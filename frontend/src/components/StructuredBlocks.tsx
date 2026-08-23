import type {
  PresentationBlock,
  PresentationCell,
  PresentationDataset,
  PresentationEnvelope,
  ReportResource,
} from '../types'
import { ReportAttachment } from './ReportAttachment'

interface StructuredBlocksProps {
  presentation: PresentationEnvelope
  fallbackText: string
  report?: ReportResource
}

function displayValue(value: PresentationCell): string {
  if (value === null) return '—'
  if (typeof value === 'number') {
    return new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 2 }).format(value)
  }
  if (typeof value === 'boolean') return value ? '是' : '否'
  return value
}

function datasetFor(
  datasets: PresentationDataset[],
  block: Exclude<PresentationBlock, { type: 'text' } | { type: 'report_attachment' }>,
): PresentationDataset | undefined {
  return datasets.find((item) => item.result_id === block.data_reference)
}

function numericSeries(
  dataset: PresentationDataset,
  xField: string,
  yField: string,
) {
  const xIndex = dataset.columns.indexOf(xField)
  const yIndex = dataset.columns.indexOf(yField)
  if (xIndex < 0 || yIndex < 0) return []
  return dataset.rows.flatMap((row) =>
    typeof row[yIndex] === 'number'
      ? [{ label: displayValue(row[xIndex]), value: row[yIndex] as number }]
      : [],
  )
}

function BarChart({ dataset, block }: {
  dataset: PresentationDataset
  block: Extract<PresentationBlock, { type: 'chart' }>
}) {
  const series = numericSeries(dataset, block.x_field, block.y_field)
  const max = Math.max(...series.map((item) => Math.abs(item.value)), 1)
  return (
    <figure className="result-chart" aria-label={`${block.title}柱状图`}>
      <figcaption>{block.title}</figcaption>
      <div className="bar-chart">
        {series.map((item, index) => (
          <div className="bar-row" key={`${item.label}-${index}`}>
            <span title={item.label}>{item.label}</span>
            <div className="bar-track">
              <i style={{ width: `${Math.max(2, Math.abs(item.value) / max * 100)}%` }} />
            </div>
            <strong>{displayValue(item.value)}</strong>
          </div>
        ))}
      </div>
    </figure>
  )
}

function LineChart({ dataset, block }: {
  dataset: PresentationDataset
  block: Extract<PresentationBlock, { type: 'chart' }>
}) {
  const series = numericSeries(dataset, block.x_field, block.y_field)
  const values = series.map((item) => item.value)
  const min = Math.min(...values, 0)
  const max = Math.max(...values, 1)
  const range = max - min || 1
  const points = series
    .map((item, index) => {
      const x = series.length === 1 ? 50 : index / (series.length - 1) * 100
      const y = 92 - (item.value - min) / range * 84
      return `${x},${y}`
    })
    .join(' ')
  return (
    <figure className="result-chart" aria-label={`${block.title}折线图`}>
      <figcaption>{block.title}</figcaption>
      <svg viewBox="0 0 100 100" role="img" aria-label={`${block.y_field}随${block.x_field}变化`} preserveAspectRatio="none">
        <line x1="0" y1="92" x2="100" y2="92" />
        <polyline points={points} />
      </svg>
      <div className="chart-axis-labels" aria-hidden="true">
        <span>{series[0]?.label}</span><span>{series.at(-1)?.label}</span>
      </div>
    </figure>
  )
}

export function StructuredBlocks({
  presentation,
  fallbackText,
  report,
}: StructuredBlocksProps) {
  const hasText = presentation.blocks.some((block) => block.type === 'text')
  return (
    <>
      {!hasText ? <p>{fallbackText}</p> : null}
      {presentation.blocks.map((block, blockIndex) => {
        if (block.type === 'text') {
          return <p key={`text-${blockIndex}`}>{block.content}</p>
        }
        if (block.type === 'report_attachment') {
          return report?.report_id === block.report_id
            ? <ReportAttachment report={report} key={`report-${block.report_id}`} />
            : null
        }
        const dataset = datasetFor(presentation.datasets, block)
        if (!dataset) return null
        if (block.type === 'metric') {
          const column = dataset.columns.indexOf(block.value_field)
          const value = dataset.rows[block.row_index]?.[column]
          return (
            <section className="result-metric" key={`metric-${blockIndex}`} aria-label={block.label}>
              <span>{block.label}</span><strong>{displayValue(value ?? null)}</strong>
            </section>
          )
        }
        if (block.type === 'table') {
          return (
            <section className="result-table-section" key={`table-${blockIndex}`}>
              <h2>{block.title}</h2>
              <div className="result-table-scroll" tabIndex={0} aria-label={`${block.title}，可横向滚动`}>
                <table>
                  <thead><tr>{dataset.columns.map((column) => <th scope="col" key={column}>{column}</th>)}</tr></thead>
                  <tbody>{dataset.rows.map((row, rowIndex) => (
                    <tr key={rowIndex}>{row.map((value, columnIndex) => <td key={`${rowIndex}-${dataset.columns[columnIndex]}`}>{displayValue(value)}</td>)}</tr>
                  ))}</tbody>
                </table>
              </div>
              {dataset.truncated ? <p className="result-note">结果较多，当前展示后端返回的前 {dataset.row_count} 行。</p> : null}
            </section>
          )
        }
        return block.visual_type === 'line'
          ? <LineChart dataset={dataset} block={block} key={`chart-${blockIndex}`} />
          : <BarChart dataset={dataset} block={block} key={`chart-${blockIndex}`} />
      })}
    </>
  )
}
