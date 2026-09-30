import type { FailureInfo } from './types'

export function publicFailureMessage(failure: FailureInfo): string {
  switch (failure.code) {
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
