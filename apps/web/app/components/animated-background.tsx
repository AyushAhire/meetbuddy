export function AnimatedBackground() {
  return (
    <div className="fixed inset-0 -z-10 pointer-events-none" aria-hidden>
      {/* Base */}
      <div className="absolute inset-0" style={{ background: "hsl(240,10%,4%)" }} />
      {/* Single very subtle top glow — common in Linear/Vercel hero sections */}
      <div
        className="absolute top-0 left-1/2 -translate-x-1/2"
        style={{
          width: 960,
          height: 480,
          background:
            "radial-gradient(ellipse at 50% 0%, hsl(245 58% 61% / 0.07) 0%, transparent 65%)",
        }}
      />
    </div>
  );
}
