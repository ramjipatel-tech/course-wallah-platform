export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`cw-skeleton rounded-xl ${className}`} />;
}

export function AppCardSkeleton() {
  return (
    <div className="cw-card p-6 space-y-4">
      <div className="flex items-center justify-between">
        <Skeleton className="w-12 h-12 rounded-xl" />
        <Skeleton className="w-16 h-5 rounded-full" />
      </div>
      <Skeleton className="w-3/4 h-5 rounded-lg" />
      <Skeleton className="w-full h-4 rounded-lg" />
      <Skeleton className="w-2/3 h-4 rounded-lg" />
    </div>
  );
}

export function BatchCardSkeleton() {
  return (
    <div className="cw-card overflow-hidden">
      <Skeleton className="w-full h-36 rounded-none" />
      <div className="p-5 space-y-3">
        <Skeleton className="w-20 h-4 rounded-full" />
        <Skeleton className="w-4/5 h-5 rounded-lg" />
        <Skeleton className="w-1/2 h-4 rounded-lg" />
      </div>
    </div>
  );
}

export function LectureCardSkeleton() {
  return (
    <div className="cw-card p-4 sm:p-5 flex items-center justify-between gap-4">
      <div className="flex items-center gap-3.5 flex-1">
        <Skeleton className="w-9 h-9 rounded-xl flex-shrink-0" />
        <div className="space-y-2 flex-1">
          <Skeleton className="w-2/3 h-4 rounded-lg" />
          <Skeleton className="w-1/3 h-3 rounded-lg" />
        </div>
      </div>
      <Skeleton className="w-28 h-9 rounded-xl flex-shrink-0" />
    </div>
  );
}
