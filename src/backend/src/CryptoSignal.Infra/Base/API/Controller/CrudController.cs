using System.Security.Claims;
using Asp.Versioning;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using CryptoSignal.Infra.Attributes;
using CryptoSignal.Infra.Base.API.Responses;
using CryptoSignal.Infra.Base.API.SearchFilter;
using CryptoSignal.Infra.Base.DB.AbstractRepo;
using CryptoSignal.Infra.Base.Entity;
using CryptoSignal.Infra.Base.Enums;
using CryptoSignal.Infra.Exceptions.Common;
using CryptoSignal.Infra.Extensions.Auth;
using CryptoSignal.Infra.Extensions.DB;
using CryptoSignal.Infra.Tooling.Logging.Adapters;
using CryptoSignal.Infra.Tooling.Mapping.Ports;
using CryptoSignal.Infra.RulesEngine;

namespace CryptoSignal.Infra.Base.API.Controller
{
    [ApiVersion("1")]
    public abstract class CrudController<TController, TInputDto, TOutputDto, TSearchDto, TEntity, TKey>(
        IRepo<TEntity> repo,
        IMapperAdapter mapper,
        ExpressionSearchFilterQuery<TEntity, TSearchDto> searchFilter,
        ILoggerAdapter<TController> logger,
        ICrudRuleExecutor<TInputDto, TEntity, TKey> crudRules) : BaseController
        where TEntity : BaseEntity<TKey>
        where TKey : struct
        where TSearchDto : class
        where TInputDto : class
        where TOutputDto : class

    {
        protected readonly ILoggerAdapter<TController> Logger = logger;
        protected readonly IMapperAdapter Mapper = mapper;


        // Base query used everywhere
        protected virtual IQueryable<TEntity> BaseQuery =>
            repo.TableNoTracking.Where(e => !e.IsDeleted);

        // Centralized projection hook
        protected virtual IQueryable<TOutputDto> Project(IQueryable<TEntity> query) =>
            Mapper.ProjectTo<TEntity, TOutputDto>(query);

        #region Hooks

        protected virtual void BeforeCreate(TEntity entity, TInputDto dto)
        {
        }

        protected virtual void BeforeUpdate(TEntity entity, TInputDto dto)
        {
        }

        protected virtual bool IsEntityInScope(TEntity entity)
        {
            return true;
        }

        #endregion

        #region Actions

        [HttpGet]
        [Permission(PermissionType.Get)]
        public virtual async Task<ApiResult<IList<TOutputDto>>> Get(CancellationToken ct)
        {
            var query = BaseQuery.OrderByDescending(e => e.CreatedAt);

            var projected = await Project(query).ToListAsync(ct);

            var res = Mapper.RemapList(projected);

            return Ok(res);
        }

        [HttpGet("{id}")]
        [Permission(PermissionType.Get)]
        public virtual async Task<ApiResult<TOutputDto>> Get(TKey id, CancellationToken ct)
        {
            var projected = await Project(BaseQuery.Where(e => e.Id.Equals(id))).FirstOrDefaultAsync(ct);
            if (projected is null)
                throw new NotFoundException();

            var res = Mapper.Remap(projected);
            return Ok(res);
        }

        [HttpGet("{page:int}/{pageSize:int}/{desc:bool}")]
        [Permission(PermissionType.Get)]
        public virtual async Task<ApiResult<PagedResult<TOutputDto>>> Get(
            [FromQuery] TSearchDto dto,
            CancellationToken ct, int page = 1, int pageSize = 10, bool desc = true)
        {
            var expression = searchFilter.CreateSearchQueryFilter(dto);
            var query = expression is null ? BaseQuery : BaseQuery.Where(expression);
            if (desc) query = query.OrderByDescending(x => x.CreatedAt);

            var projected = Project(query);
            var paged = await projected.ToPagedResultAsync(page, pageSize, ct);

            var finalPaged = Mapper.RemapPaged(paged);

            return Ok(finalPaged);
        }

        [HttpPost]
        [Permission(PermissionType.Create)]
        public virtual async Task<ApiResult<TOutputDto?>> Create(TInputDto dto, CancellationToken ct)
        {
            var entity = Mapper.Map<TEntity>(dto);

            BeforeCreate(entity, dto);

            await crudRules.ValidateCreateAsync(
                dto,
                entity,
                ct);
            
            await repo.AddAsync(entity, cancellationToken: ct);

            var resultDto = Mapper.Map<TOutputDto>(entity);

            Logger.Debug($"Created {typeof(TEntity).Name} with ID {entity.Id}");

            return resultDto;
        }

        [HttpPut("{id}")]
        [Permission(PermissionType.Update)]
        public virtual async Task<ApiResult<TOutputDto?>> Update(TKey id, TInputDto dto,
            CancellationToken cancellationToken)
        {
            var entity = await repo.GetByIdAsync(cancellationToken, id);
            if (entity is null || !IsEntityInScope(entity))
                throw new NotFoundException();

            await crudRules.ValidateUpdateAsync(
                id,
                dto,
                entity,
                cancellationToken);
            
            entity = Mapper.MapInto(dto, entity);
            entity.Id = id;

            BeforeUpdate(entity, dto);
            

            await repo.UpdateAsync(entity, cancellationToken: cancellationToken);

            var resultDto = Mapper.Map<TOutputDto>(entity);

            Logger.Debug($"Updated {typeof(TEntity).Name} with ID {id}");

            return resultDto;
        }

        [HttpDelete("{id}")]
        [Permission(PermissionType.Delete)]
        public virtual async Task<ApiResult> Delete(TKey id, CancellationToken ct)
        {
            var entity = await repo.GetByIdAsync(ct, id);
            if (entity is null || !IsEntityInScope(entity))
                throw new NotFoundException();
            
            await crudRules.ValidateDeleteAsync(
                id,
                entity,
                ct);
            
            await repo.SoftDeleteAsync(entity, cancellationToken: ct);

            Logger.Debug($"Deleted {typeof(TEntity).Name} with ID {id}");

            return Ok();
        }

        // [HttpDelete("{id}")]
        // [Permission(PermissionType.Delete)]
        // public virtual async Task<ApiResult> Delete(TKey id, CancellationToken cancellationToken)
        // {
        //     var entity = await repo.GetByIdAsync(cancellationToken, id);
        //     if (entity is null)
        //         throw new NotFoundException();
        //
        //     await repo.de(entity, cancellationToken);
        //     Logger.Info($"Hard-deleted {typeof(TEntity).Name} with ID {id}");
        //     return Ok();
        // }

        #endregion
    }
}