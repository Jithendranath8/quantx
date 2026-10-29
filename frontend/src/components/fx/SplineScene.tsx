import React, { Suspense, lazy, useEffect, useState } from 'react';

// The Spline runtime is ~1 MB; loading it lazily keeps it off the app's
// critical path, so only the home page ever downloads it.
const Spline = lazy(() => import('@splinetool/react-spline'));

/** Interactive 3D robot that tracks the cursor. */
export const ROBOT_SCENE = 'https://prod.spline.design/kZDDjO5HuC9GJUM2/scene.splinecode';

class SceneBoundary extends React.Component<{ fallback: React.ReactNode; children: React.ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}

/** Static stand-in shown while loading, on failure, and for reduced motion. */
function SceneFallback() {
  return (
    <div className="absolute inset-0 grid place-items-center" aria-hidden="true">
      <div className="relative w-64 h-64">
        <div className="absolute inset-0 rounded-full border border-brand-500/20" />
        <div className="absolute inset-8 rounded-full border border-white/10" />
        <div className="absolute inset-16 rounded-full border border-brand-500/30 animate-pulse" />
        <div className="absolute inset-[6.5rem] rounded-full bg-brand-500/30 blur-xl" />
      </div>
    </div>
  );
}

export default function SplineScene({ scene = ROBOT_SCENE, className = '' }: { scene?: string; className?: string }) {
  const [enabled, setEnabled] = useState(false);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    // Honour reduced-motion and skip WebGL on small screens, where it costs
    // battery for decoration the layout hides anyway.
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const wide = window.matchMedia('(min-width: 1024px)').matches;
    setEnabled(!reduce && wide);
  }, []);

  return (
    <div className={`relative ${className}`}>
      {!loaded && <SceneFallback />}
      {enabled && (
        <SceneBoundary fallback={null}>
          <Suspense fallback={null}>
            <Spline
              scene={scene}
              onLoad={() => setLoaded(true)}
              className={`!w-full !h-full transition-opacity duration-1000 ${loaded ? 'opacity-100' : 'opacity-0'}`}
            />
          </Suspense>
        </SceneBoundary>
      )}
    </div>
  );
}
