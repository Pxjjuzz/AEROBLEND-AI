"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

interface NavItem {
  name: string;
  href: string;
  icon: string;
}

const mainNavItems: NavItem[] = [
  { name: "Overview", href: "/", icon: "home" },
  { name: "Forecast", href: "/forecast", icon: "rainy" },
  { name: "Live Globe", href: "/live-globe", icon: "public" },
  { name: "Models", href: "/models", icon: "layers" },
  { name: "Analytics", href: "/analytics", icon: "bar_chart" },
  { name: "Extreme Events", href: "/extreme-events", icon: "warning" },
  { name: "Alerts", href: "/alerts", icon: "notifications" },
  { name: "Data Sources", href: "/data-sources", icon: "database" },
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="fixed left-0 top-0 h-full w-64 z-50 flex flex-col p-space-md select-none">
      <div className="h-full w-full bg-surface-container-lowest/70 backdrop-blur-xl rounded-2xl shadow-[0_20px_40px_-15px_rgba(15,23,42,0.05)] flex flex-col justify-between p-space-md border border-white/60">
        <div className="flex flex-col gap-space-md">
          {/* Brand Header */}
          <Link href="/" className="flex items-center gap-space-sm px-space-xs py-space-xs group">
            <div className="w-8 h-8 rounded-lg overflow-hidden flex items-center justify-center shrink-0">
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 40" className="w-8 h-8" fill="none">
                <defs>
                  <linearGradient id="cloudGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stopColor="#3B82F6" />
                    <stop offset="50%" stopColor="#60A5FA" />
                    <stop offset="100%" stopColor="#93C5FD" />
                  </linearGradient>
                  <linearGradient id="aiBlend" x1="0%" y1="100%" x2="100%" y2="0%">
                    <stop offset="0%" stopColor="#6366F1" stopOpacity="0.8" />
                    <stop offset="100%" stopColor="#06B6D4" stopOpacity="0.9" />
                  </linearGradient>
                </defs>
                <circle cx="16" cy="20" r="10" fill="url(#cloudGrad)" opacity="0.9" />
                <circle cx="24" cy="16" r="8" fill="url(#aiBlend)" opacity="0.85" />
                <path d="M10 26C10 22 13 20 16 20C17 16 20 14 24 14C28 14 31 17 31 21C34 21 36 23 36 26C36 28.5 34 30 31 30H14C11.5 30 10 28.5 10 26Z" fill="url(#cloudGrad)" />
                <path d="M14 24C18 21 22 27 26 23C28 21 31 23 33 22" stroke="#FFFFFF" strokeWidth="1.8" strokeLinecap="round" opacity="0.95" />
                <circle cx="26" cy="23" r="1.8" fill="#FFFFFF" />
              </svg>
            </div>
            <div className="flex flex-col">
              <span className="font-headline-sm text-headline-sm text-on-surface tracking-tight leading-none">
                AeroBlend
              </span>
              <span className="font-label-sm text-[10px] text-primary uppercase tracking-widest font-bold">
                AI Engine
              </span>
            </div>
          </Link>

          <div className="h-px w-full bg-surface-variant/40" />

          {/* Navigation Links */}
          <nav className="flex flex-col gap-1">
            {mainNavItems.map((item) => {
              const isActive = pathname === item.href;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`flex items-center gap-space-sm px-space-md py-space-sm rounded-xl transition-all group ${
                    isActive
                      ? "bg-surface-container-lowest text-primary shadow-[0_4px_16px_-4px_rgba(37,99,235,0.18)] font-label-lg font-bold border-l-4 border-primary pl-space-sm"
                      : "text-on-surface-variant hover:bg-surface-container-high/60 hover:text-on-surface"
                  }`}
                >
                  <span
                    className={`material-symbols-outlined text-[20px] transition-colors ${
                      isActive ? "text-primary" : "text-outline group-hover:text-primary"
                    }`}
                  >
                    {item.icon}
                  </span>
                  <span className="font-label-lg text-label-lg">{item.name}</span>
                </Link>
              );
            })}
          </nav>
        </div>

        {/* Footer Area with Settings and Stream Health */}
        <div className="flex flex-col gap-space-sm pt-space-md border-t border-surface-variant/40">
          <Link
            href="/settings"
            className={`flex items-center gap-space-sm px-space-md py-space-sm rounded-xl transition-all group ${
              pathname === "/settings"
                ? "bg-surface-container-lowest text-primary shadow-[0_4px_16px_-4px_rgba(37,99,235,0.18)] font-label-lg font-bold border-l-4 border-primary pl-space-sm"
                : "text-on-surface-variant hover:bg-surface-container-high/60 hover:text-on-surface"
            }`}
          >
            <span
              className={`material-symbols-outlined text-[20px] transition-colors ${
                pathname === "/settings" ? "text-primary" : "text-outline group-hover:text-primary"
              }`}
            >
              tune
            </span>
            <span className="font-label-lg text-label-lg">Settings</span>
          </Link>

          <div className="flex items-center justify-between px-space-sm py-space-xs rounded-xl bg-surface-container-low/70">
            <div className="flex items-center gap-space-xs">
              <span className="w-2 h-2 rounded-full bg-secondary animate-pulse" />
              <span className="font-label-sm text-label-sm text-on-surface-variant">NWP Stream</span>
            </div>
            <span className="font-code-sm text-code-sm text-secondary font-bold">99.98%</span>
          </div>
        </div>
      </div>
    </aside>
  );
}
