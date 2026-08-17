import { useEffect, useState } from 'react'

type Platform = {
  operatingMode: string
  executionPolicy: string
}

type Readiness = {
  status: string
  dependencies: Array<{ name: string; status: string }>
}

const services = [
  { name: 'Orchestrator', detail: '.NET 10 API', key: 'api' },
  { name: 'ML Engine', detail: 'Python compute service', key: 'ml' },
  { name: 'Database', detail: 'PostgreSQL 18', key: 'db' },
]

export default function App() {
  const [platform, setPlatform] = useState<Platform | null>(null)
  const [readiness, setReadiness] = useState<Readiness | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([
      fetch('/api/v1/platform').then((response) => response.json()),
      fetch('/health/ready').then((response) => response.json()),
    ])
      .then(([platformData, readinessData]) => {
        setPlatform(platformData)
        setReadiness(readinessData)
      })
      .catch(() => setError('The orchestration API is not reachable.'))
  }, [])

  const mlStatus = readiness?.dependencies.find(
    (dependency) => dependency.name === 'python-ml',
  )?.status

  return (
    <main className="shell">
      <header className="hero">
        <div>
          <p className="eyebrow">CRYPTO SIGNAL / OPERATIONS</p>
          <h1>Trading intelligence,<br />under control.</h1>
          <p className="lede">
            One operational surface for models, wallets, risk, orders, and exchange execution.
          </p>
        </div>
        <div className="mode-card">
          <span>OPERATING MODE</span>
          <strong>{platform?.operatingMode ?? 'PAPER'}</strong>
          <small>Exchange execution is disabled by default</small>
        </div>
      </header>

      {error && <div className="alert">{error}</div>}

      <section className="service-grid" aria-label="Platform services">
        {services.map((service) => {
          const status = service.key === 'ml' ? mlStatus : readiness?.status
          return (
            <article className="service-card" key={service.key}>
              <div className="status-row">
                <span className={`dot ${status === 'healthy' ? 'healthy' : ''}`} />
                <span>{status ?? 'connecting'}</span>
              </div>
              <h2>{service.name}</h2>
              <p>{service.detail}</p>
            </article>
          )
        })}
      </section>

      <section className="boundary-card">
        <p className="eyebrow">EXECUTION BOUNDARY</p>
        <h2>{platform?.executionPolicy ?? 'The .NET orchestrator owns every execution decision.'}</h2>
        <div className="flow">
          <span>React dashboard</span><b>→</b><span>.NET orchestrator</span><b>→</b><span>Exchange adapter</span>
        </div>
        <div className="flow muted">
          <span>Market data</span><b>→</b><span>Python ML</span><b>→</b><span>Signal only</span>
        </div>
      </section>
    </main>
  )
}
