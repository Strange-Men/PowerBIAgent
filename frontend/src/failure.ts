import type { FailureInfo } from './types'

export function publicFailureMessage(failure: FailureInfo): string {
  switch (failure.code) {
    case 'AUTH_REQUIRED':
      return '请使用 Microsoft 账号登录。'
    case 'AUTH_EXPIRED':
      return '登录已过期，请重新登录。'
    case 'AUTH_CONSENT_REQUIRED':
      return '需要批准才能继续，请登录或联系管理员。'
    case 'AUTH_FORBIDDEN':
      return '当前账号暂时无法访问，请切换账号或联系管理员。'
    case 'RESOURCE_NOT_ACCESSIBLE':
      return '当前账号无法访问这个数据模型，请切换账号或联系管理员。'
    case 'MODEL_RESOLUTION_FAILED':
    case 'SCHEMA_UNAVAILABLE':
      return '暂时无法读取这个数据模型，请刷新目录后重新选择。'
    case 'QUERY_REJECTED':
      return '云端数据服务无法完成本次查询，请调整问题后重试。'
    case 'QUERY_TIMEOUT':
      return '云端数据服务响应超时，请重试。'
    case 'RATE_LIMITED':
      return '云端数据服务请求较多，请稍后重试。'
    case 'UPSTREAM_UNAVAILABLE':
      return '云端数据服务暂不可用，请稍后重试。'
    case 'CONTRACT_DRIFT':
      return '云端数据响应暂时无法验证，请联系管理员。'
    case 'REPORT_TEMPLATE_INCOMPATIBLE':
      return '当前数据模型不支持这个报表模板，请选择其他模板或数据模型。'
    case 'REPORT_TEMPLATE_UNAVAILABLE':
      return '当前报表模板已失效，请重新选择。'
    case 'REPORT_DATA_UNAVAILABLE':
      return '当前数据无法生成该报表，请调整问题后重试。'
    case 'REPORT_EXECUTION_FAILED':
      return '报表数据查询未完成，请稍后重试。'
    case 'REPORT_RENDER_FAILED':
      return '数据查询已完成，但报表生成失败，请重试生成报表。'
    case 'POWERBI_CONNECTION_LOST':
      return 'Power BI Desktop 连接已中断，请重新打开数据模型并刷新。'
    case 'SEMANTIC_MODEL_STALE':
      return '当前选择的数据模型已关闭或失效，请刷新后重新选择。'
    case 'LLM_SERVICE_UNAVAILABLE':
      return 'AI 分析服务暂不可用，请稍后重试。'
    case 'REQUEST_TIMEOUT':
      return '本次分析超时，请重试。'
    case 'VALIDATION_FAILED':
      return '当前数据无法完成该分析，请调整问题后重试。'
    case 'INTERNAL_FAILURE':
      return '当前请求暂时无法完成，请稍后重试。'
    default:
      return '当前请求暂时无法完成，请稍后重试。'
  }
}
