import { useEffect, useState } from "react";
import { NavLink, Link, useLocation } from "react-router-dom";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faHouse,
  faComment,
  faListCheck,
  faFileInvoiceDollar,
  faEllipsis,
  faBuildingColumns,
  faEnvelope,
  faGear,
  faChevronRight,
} from "@fortawesome/free-solid-svg-icons";
import { fetchReviewQueue } from "../services/reviewQueueService";
import { getSessionUserId } from "../services/bankService";

// Auth, onboarding and Chat go without the tab bar. Chat needs the full height
// for the composer, and it has its own back button and menu in the header.
const HIDDEN_ON = ["/", "/signup", "/onboarding", "/chat", "/business"];
const MORE_ROUTES = ["/accounts", "/settings", "/gmail-connect"];
const REFRESH_MS = 60_000;

const MORE_LINKS = [
  { to: "/accounts", label: "Bank accounts", hint: "Balances and connected banks", icon: faBuildingColumns },
  { to: "/gmail-connect", label: "Gmail", hint: "Sync your bank alert emails", icon: faEnvelope },
  { to: "/settings", label: "Settings", hint: "Account, notifications, data", icon: faGear },
];

const tabClass = (active) =>
  `group flex min-h-11 min-w-11 flex-1 select-none flex-col items-center justify-center gap-0.5 rounded-xl px-1 py-1 text-[10.5px] font-medium outline-none [-webkit-tap-highlight-color:transparent] focus-visible:ring-2 focus-visible:ring-loamy-700 ${
    active ? "text-loamy-700" : "text-gray-500"
  }`;

// Material-style indicator: only the icon sits in a pill, not the whole tab.
const pillClass = (active) =>
  `flex h-7 w-14 items-center justify-center rounded-full transition-colors group-active:bg-loamy-100 ${
    active ? "bg-loamy-100" : ""
  }`;

function useReviewCount(enabled, pathname) {
  const [count, setCount] = useState(0);

  useEffect(() => {
    if (!enabled) return undefined;
    let cancelled = false;
    const load = () =>
      fetchReviewQueue(getSessionUserId())
        .then((res) => {
          if (!cancelled && res.status === "success") setCount((res.data?.items || []).length);
        })
        .catch(() => {});
    load();
    const timer = setInterval(load, REFRESH_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [enabled, pathname]);

  return count;
}

export default function MobileNav() {
  const { pathname } = useLocation();
  const [moreOpen, setMoreOpen] = useState(false);
  const visible = !HIDDEN_ON.includes(pathname);
  const reviewCount = useReviewCount(visible, pathname);

  useEffect(() => {
    if (!moreOpen) return undefined;
    const onKey = (e) => e.key === "Escape" && setMoreOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [moreOpen]);

  if (!visible) return null;

  const moreActive = MORE_ROUTES.some((r) => pathname.startsWith(r));
  const reviewLabel = reviewCount > 0 ? `Review, ${reviewCount} to review` : "Review";

  return (
    <>
      <nav
        className="z-40 flex shrink-0 items-stretch gap-1 border-t border-black/5 bg-white/90 px-2 pt-1.5 pb-[max(0.25rem,env(safe-area-inset-bottom))] backdrop-blur-md min-[769px]:hidden"
        aria-label="Primary"
      >
        <NavLink to="/dashboard" className={({ isActive }) => tabClass(isActive || pathname === "/spending")}>
          {({ isActive }) => (
            <>
              <span className={pillClass(isActive || pathname === "/spending")}>
                <FontAwesomeIcon icon={faHouse} className="text-base" />
              </span>
              <span>Home</span>
            </>
          )}
        </NavLink>
        <NavLink to="/chat" className={({ isActive }) => tabClass(isActive)}>
          {({ isActive }) => (
            <>
              <span className={pillClass(isActive)}>
                <FontAwesomeIcon icon={faComment} className="text-base" />
              </span>
              <span>Chat</span>
            </>
          )}
        </NavLink>
        <NavLink to="/review-queue" aria-label={reviewLabel} className={({ isActive }) => tabClass(isActive)}>
          {({ isActive }) => (
            <>
              <span className={`relative ${pillClass(isActive)}`}>
                <FontAwesomeIcon icon={faListCheck} className="text-base" />
                {reviewCount > 0 && (
                  <span
                    className="absolute top-0 right-2 min-w-4 rounded-full bg-red-600 px-1 text-center text-[9px] font-bold leading-4 text-white"
                    aria-hidden="true"
                  >
                    {reviewCount > 99 ? "99+" : reviewCount}
                  </span>
                )}
              </span>
              <span>Review</span>
            </>
          )}
        </NavLink>
        <NavLink to="/invoices" className={({ isActive }) => tabClass(isActive)}>
          {({ isActive }) => (
            <>
              <span className={pillClass(isActive)}>
                <FontAwesomeIcon icon={faFileInvoiceDollar} className="text-base" />
              </span>
              <span>Invoices</span>
            </>
          )}
        </NavLink>
        <button
          type="button"
          className={tabClass(moreActive || moreOpen)}
          aria-haspopup="dialog"
          aria-expanded={moreOpen}
          onClick={() => setMoreOpen((open) => !open)}
        >
          <span className={pillClass(moreActive || moreOpen)}>
            <FontAwesomeIcon icon={faEllipsis} className="text-base" />
          </span>
          <span>More</span>
        </button>
      </nav>

      {moreOpen && (
        <div
          className="fixed inset-0 z-50 flex animate-fade-in items-end bg-black/40 min-[769px]:hidden"
          onClick={() => setMoreOpen(false)}
        >
          <div
            className="w-full animate-sheet-up rounded-t-3xl bg-white px-4 pt-2 pb-[max(1rem,env(safe-area-inset-bottom))] shadow-sm"
            role="dialog"
            aria-modal="true"
            aria-label="More"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mx-auto mb-3 h-1 w-10 rounded-full bg-gray-300" aria-hidden="true" />
            {MORE_LINKS.map(({ to, label, hint, icon }) => (
              <Link
                key={to}
                to={to}
                className="flex min-h-14 items-center gap-3 rounded-2xl p-2 transition-transform active:scale-[0.98] active:bg-gray-50"
                onClick={() => setMoreOpen(false)}
              >
                <span className="flex size-11 shrink-0 items-center justify-center rounded-2xl bg-loamy-100 text-loamy-700">
                  <FontAwesomeIcon icon={icon} />
                </span>
                <span className="flex min-w-0 flex-1 flex-col">
                  <strong className="text-sm font-semibold text-gray-900">{label}</strong>
                  <small className="truncate text-xs text-gray-500">{hint}</small>
                </span>
                <FontAwesomeIcon icon={faChevronRight} className="text-xs text-gray-400" />
              </Link>
            ))}
          </div>
        </div>
      )}
    </>
  );
}
