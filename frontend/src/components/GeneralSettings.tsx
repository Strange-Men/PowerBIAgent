import { useTranslation } from 'react-i18next'
import { LanguageSwitch } from './LanguageSwitch'
import { tr } from '../i18n'

export function GeneralSettings() {
  useTranslation()
  return <section className="settings-intro general-settings">
    <h3>{tr('resources:general')}</h3>
    <div className="settings-preference-row">
      <span>{tr('common:language')}</span>
      <LanguageSwitch />
    </div>
  </section>
}
