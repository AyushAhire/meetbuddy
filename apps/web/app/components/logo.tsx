export function Logo({ size = 20 }: { size?: number }) {
  const stroke = Math.max(2, size * 0.078);
  return (
    <div
      className="rounded flex items-center justify-center flex-shrink-0"
      style={{ width: size, height: size, background: "#080A0E", border: "1px solid #1a1f2e" }}
    >
      <svg
        viewBox="0 0 32 32"
        fill="none"
        style={{ width: size * 0.85, height: size * 0.85 }}
      >
        <line x1="5"  y1="16" x2="5"  y2="16" stroke="#3D7BFF" strokeWidth={stroke} strokeLinecap="round" />
        <line x1="10" y1="12" x2="10" y2="20" stroke="#3D7BFF" strokeWidth={stroke} strokeLinecap="round" />
        <line x1="16" y1="7"  x2="16" y2="25" stroke="#3D7BFF" strokeWidth={stroke} strokeLinecap="round" />
        <line x1="22" y1="11" x2="22" y2="21" stroke="#3D7BFF" strokeWidth={stroke} strokeLinecap="round" />
        <line x1="27" y1="14" x2="27" y2="18" stroke="#3D7BFF" strokeWidth={stroke} strokeLinecap="round" />
      </svg>
    </div>
  );
}
