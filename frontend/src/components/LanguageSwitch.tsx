import { useTranslation } from 'react-i18next'
import { normalizeLocale, setLocale } from '../i18n'

export function LanguageSwitch() {
  const {t, i18n} = useTranslation()
  return <select className="language-switch" aria-label={t('language')}
    value={normalizeLocale(i18n.language)} onChange={event=>void setLocale(event.target.value)}>
    <option value="zh-CN">{t('chinese')}</option>
    <option value="en-US">{t('english')}</option>
  </select>
}
