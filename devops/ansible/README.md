# Ansible — multi-environment deploy for crypto-signal

```
devops/ansible/
├── ansible.cfg            # inventory default (dev), vault password via --vault-password-file
├── site.yml               # FRESH INSTALL: prereq -> checkout -> envfiles -> compose -> health
├── upgrade.yml            # VERSION UPGRADE: checkout -> backup -> envfiles -> compose -> health
├── inventories/
│   ├── dev/hosts.yml      # localhost (compose.yml + compose.dev.yml)
│   ├── prod/hosts.yml     # self-hosted (compose.yml + compose.prod.yml)
│   └── aws/hosts.yml      # EC2 + RDS (compose.yml + compose.prod.yml + compose.aws.yml)
├── group_vars/
│   ├── all.yml            # app_dir, repo_url, health gate
│   ├── dev.yml            # compose files + non-secret env for dev
│   ├── prod.yml           # … for prod
│   ├── aws.yml            # … for aws (manage_db_container: false)
│   └── vault.example.yml  # copy to <env>/vault.yml + `ansible-vault encrypt`
└── roles/
    ├── prereq/            # docker engine + compose plugin (Debian/Ubuntu)
    ├── checkout/          # git clone/pull @ app_version, stamps .ansible-deployed-version
    ├── envfiles/          # templates api/ml/db.env (mode 0600, vault secrets)
    ├── compose/           # build + up, ALWAYS injecting Jwt/KEK/ML-endpoint env
    ├── backup/            # pg_dump pre-upgrade (local-db envs only; RDS snapshots are in-console)
    └── health/            # /health/ready gate + unhealthy-container fail
```

## First-time setup (control node)

```bash
pip install ansible-core  # or pipx install ansible-core
echo 'my-vault-password' > ~/.ansible/vault-pass && chmod 600 ~/.ansible/vault-pass
cp group_vars/vault.example.yml group_vars/aws/vault.yml
# fill every CHANGEME, then:
ansible-vault encrypt group_vars/aws/vault.yml
```

Key generation (run on the TARGET or any trusted box, paste values into vault):

```bash
openssl rand -base64 48  # API_Settings__Jwt__SecretKey (rotation = dashboard re-login only)
openssl rand -base64 32  # Sercurity__KeyEncryptionKey — MUST decode to exactly 32 bytes
```

## Fresh install

```bash
cd devops/ansible
ansible-playbook -i inventories/aws/hosts.yml site.yml -e app_version=v1.2.0
```

## Upgrade

```bash
ansible-playbook -i inventories/aws/hosts.yml upgrade.yml -e app_version=v1.3.0
# single service, skip build (config-only change):
ansible-playbook -i inventories/aws/hosts.yml upgrade.yml \
  -e "app_version=v1.3.0 compose_services=dashboard compose_build=false"
# rollback = upgrade to the previous SHA:
ansible-playbook -i inventories/aws/hosts.yml upgrade.yml -e app_version=<sha-from-.ansible-deployed-version>
```

## Why the compose role injects env (read before "simplifying")

2026-09-10: a bare `docker compose up -d api` recreated the container and dropped
three values that live in NO compose file — api crash-looped (exit 134, missing
Jwt), then failed KEK validation, then failed every ML scan (gRPC Unavailable).
The compose role passes all three on every `up` so recreates are always safe.
`group_vars/*/aws.yml` documents the same lesson; so does the crypto-signal-ops
skill ("Deploying a recreated container" section).

## .gitignore (add at repo root)

```
devops/ansible/group_vars/*/vault.yml
devops/ansible/*.retry
```

## Not covered

- RDS snapshots (AWS console), Cloudflare/DNS, OS hardening beyond docker.
- Exchange API keys: re-entered per environment via the dashboard (per-env KEK).
