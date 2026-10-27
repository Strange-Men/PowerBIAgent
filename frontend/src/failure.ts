import { tr } from './i18n'
import type { FailureInfo } from './types'

export type CloudDenialReason = 'test_scope_missing' | 'cloud_execution_blocked' | 'cloud_disclosure_blocked' | 'cloud_persistence_blocked'

export function cloudDenialMessage(reason: CloudDenialReason, productMode = false): string {
  switch (reason) {
    case 'test_scope_missing': return tr('errors:signedInTheApprovedTestResourceListIsNot')
    case 'cloud_disclosure_blocked': return tr('errors:signedInCloudBusinessDataIsNotApprovedFor')
    case 'cloud_persistence_blocked': return tr('errors:signedInCloudBusinessHistoryAndReportStorageAre')
    default: return productMode ? tr('errors:modelAccessRequiresVerification') : tr('errors:signedInCloudBusinessAcceptanceIsIncompleteAnalysisAnd')
  }
}

export function cloudFailureAction(error: {status: number; failure?: FailureInfo; denialReason?: CloudDenialReason}): 'auth' | 'resource' | 'blocked' | 'conflict' | 'recoverable' {
  if (error.status===401 || ['AUTH_REQUIRED','AUTH_EXPIRED'].includes(error.failure?.code || '')) return 'auth'
  if (error.denialReason) return 'blocked'
  if (error.failure?.code==='RESOURCE_NOT_ACCESSIBLE') return 'resource'
  if (!error.failure && [403,404].includes(error.status)) return 'resource'
  if (error.status===409) return 'conflict'
  return 'recoverable'
}

export function resourceFailureMessage(code: string): string {
  switch (code) {
    case 'RESOURCE_NOT_FOUND':
      return tr('errors:thisConversationOrReportNoLongerExists')
    case 'RESOURCE_NOT_ACCESSIBLE':
      return tr('errors:thisAccountCannotAccessThisDataModelSwitchAccounts')
    case 'PERSISTENCE_UNAVAILABLE':
      return tr('errors:persistenceUnavailable')
    default:
      return tr('resources:theOperationWasNotCompletedTryAgainLater')
  }
}

export function publicFailureMessage(failure: FailureInfo): string {
  switch (failure.code) {
    case 'AUTH_REQUIRED':
      return tr('errors:pleaseSignInWithYourMicrosoftAccount')
    case 'AUTH_EXPIRED':
      return tr('auth:yourSessionHasExpiredSignInAgain')
    case 'AUTH_CONSENT_REQUIRED':
      return tr('auth:approvalIsRequiredSignInOrContactYourAdministrator')
    case 'AUTH_FORBIDDEN':
      return tr('errors:thisAccountCannotAccessTheServiceSwitchAccountsOr')
    case 'RESOURCE_NOT_ACCESSIBLE':
      return tr('errors:thisAccountCannotAccessThisDataModelSwitchAccounts')
    case 'MODEL_RESOLUTION_FAILED':
    case 'SCHEMA_UNAVAILABLE':
      return tr('errors:cannotReadThisModelRefreshTheCatalogAndSelect')
    case 'QUERY_REJECTED':
      return tr('errors:theCloudDataServiceCouldNotCompleteThisQuery')
    case 'QUERY_TIMEOUT':
      return tr('errors:theCloudDataServiceTimedOutTryAgain')
    case 'RATE_LIMITED':
      return tr('errors:theCloudDataServiceIsBusyTryAgainLater')
    case 'UPSTREAM_UNAVAILABLE':
      return tr('errors:theCloudDataServiceIsUnavailableTryAgainLater')
    case 'CONTRACT_DRIFT':
      return tr('errors:theCloudDataResponseCouldNotBeVerifiedContact')
    case 'REPORT_TEMPLATE_INCOMPATIBLE':
      return tr('errors:thisModelDoesNotSupportThisReportTemplateChoose')
    case 'REPORT_TEMPLATE_UNAVAILABLE':
      return tr('errors:thisReportTemplateIsNoLongerAvailableSelectIt')
    case 'REPORT_DATA_UNAVAILABLE':
      return tr('errors:thisDataCannotSupportTheReportAdjustYourQuestion')
    case 'REPORT_EXECUTION_FAILED':
      return tr('errors:theReportDataQueryWasNotCompletedTryAgain')
    case 'REPORT_RENDER_FAILED':
      return tr('errors:theDataQuerySucceededButReportRenderingFailedTry')
    case 'POWERBI_CONNECTION_LOST':
      return tr('errors:thePowerBiDesktopConnectionWasLostReopenThe')
    case 'SEMANTIC_MODEL_STALE':
      return tr('errors:theSelectedDataModelIsNoLongerAvailableRefresh79919f')
    case 'LLM_SERVICE_UNAVAILABLE':
      return tr('errors:theAiAnalysisServiceIsUnavailableTryAgainLater')
    case 'REQUEST_TIMEOUT':
      return tr('errors:thisAnalysisTimedOutTryAgain')
    case 'VALIDATION_FAILED':
      return tr('errors:thisDataCannotSupportTheAnalysisAdjustYourQuestion')
    case 'PERSISTENCE_UNAVAILABLE':
      return tr('errors:persistenceUnavailable')
    case 'PERSISTENCE_SCHEMA_OUTDATED':
      return tr('errors:persistenceSchemaOutdated')
    case 'INTERNAL_FAILURE':
      return tr('errors:thisRequestCannotBeCompletedRightNowTryAgain')
    default:
      return tr('errors:thisRequestCannotBeCompletedRightNowTryAgain')
  }
}
