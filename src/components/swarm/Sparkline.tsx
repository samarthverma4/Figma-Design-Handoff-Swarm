interface Props { values: number[]; color: string; }
export function Sparkline({ values, color }: Props) {
  const w = 120, h = 22;
  const step = w / (values.length - 1);
  const path = values
    .map((v, i) => `${i === 0 ? "M" : "L"} ${(i * step).toFixed(1)} ${(h - v * h).toFixed(1)}`)
    .join(" ");
  return (
    <svg width={w} height={h} className="overflow-visible">
      <path d={path} fill="none" stroke={color} strokeWidth="1.25" strokeLinecap="round" strokeLinejoin="round" opacity={0.9} />
    </svg>
  );
}
