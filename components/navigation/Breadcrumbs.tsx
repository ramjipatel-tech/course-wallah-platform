import Link from "next/link";
import { ChevronRight, Home } from "lucide-react";

export interface BreadcrumbItem {
  label: string;
  href?: string;
}

export function Breadcrumbs({ items }: { items: BreadcrumbItem[] }) {
  return (
    <nav className="flex items-center text-xs sm:text-sm text-cw-muted py-3 px-1 overflow-x-auto whitespace-nowrap" aria-label="Breadcrumb">
      <Link href="/" className="flex items-center hover:text-white transition-colors text-cw-muted/90">
        <Home className="w-3.5 h-3.5 mr-1.5 text-cw-primary" />
        <span>Home</span>
      </Link>
      {items.map((item, idx) => (
        <div key={idx} className="flex items-center">
          <ChevronRight className="w-3.5 h-3.5 mx-2 text-cw-muted/50 flex-shrink-0" />
          {item.href ? (
            <Link href={item.href} className="hover:text-white transition-colors text-cw-muted/90">
              {item.label}
            </Link>
          ) : (
            <span className="text-white font-semibold truncate max-w-xs">{item.label}</span>
          )}
        </div>
      ))}
    </nav>
  );
}
