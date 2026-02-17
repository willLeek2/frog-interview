import type { FeatureType } from '../lib/types'

const FEATURE_LABELS: Record<FeatureType, string> = {
  random: '随机抽题',
  explain: '解释知识点',
  quiz: '出题训练',
  experience: '面经挖掘',
}

interface Props {
  current: FeatureType
  onChange: (value: FeatureType) => void
}

export default function FeatureMenu({ current, onChange }: Props) {
  const features = Object.keys(FEATURE_LABELS) as FeatureType[]

  return (
    <div className="space-y-2">
      {features.map((feature) => {
        const active = feature === current
        return (
          <button
            key={feature}
            onClick={() => onChange(feature)}
            className={`w-full rounded-xl px-3 py-2 text-left text-sm transition ${
              active
                ? 'bg-primary-600 text-white shadow-soft'
                : 'bg-white text-primary-800 hover:bg-primary-50'
            }`}
          >
            {FEATURE_LABELS[feature]}
          </button>
        )
      })}
    </div>
  )
}
