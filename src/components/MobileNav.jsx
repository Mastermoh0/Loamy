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
import "./MobileNav.css";

// The chat page has its own slide-in drawer and needs the full height for the
// composer, so the tab bar stays out of its way (as do the auth/onboarding flows).
const HIDDEN_ON = ["/", "/signup", "/onboarding", "/chat", "/gmail-connect"];
const MORE_ROUTES = ["/accounts", "/settings", "/gmail-connect"];
const REFRESH_MS = 60_000;

const MORE_LINKS = [
  { to: "/accounts", label: "Bank accounts", hint: "Balances and connected banks", icon: faBuildingColumns },
  { to: "/gmail-connect", label: "Gmail", hint: "Sync your bank alert emails", icon: faEnvelope },
  { to: "/settings", label: "Settings", hint: "Account, notifications, data", icon: faGear },
];

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
    document.body.classList.toggle("has-mobile-nav", visible);
    return () => document.body.classList.remove("has-mobile-nav");
  }, [visible]);

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
      <nav className="mobile-nav" aria-label="Primary">
        <NavLink to="/dashboard" className={({ isActive }) => `mobile-tab${isActive || pathname === "/spending" ? " active" : ""}`}>
          <FontAwesomeIcon icon={faHouse} />
          <span>Home</span>
        </NavLink>
        <NavLink to="/chat" className={({ isActive }) => `mobile-tab${isActive ? " active" : ""}`}>
          <FontAwesomeIcon icon={faComment} />
          <span>Chat</span>
        </NavLink>
        <NavLink
          to="/review-queue"
          aria-label={reviewLabel}
          className={({ isActive }) => `mobile-tab${isActive ? " active" : ""}`}
        >
          <span className="mobile-tab-icon">
            <FontAwesomeIcon icon={faListCheck} />
            {reviewCount > 0 && (
              <span className="mobile-tab-badge" aria-hidden="true">
                {reviewCount > 99 ? "99+" : reviewCount}
              </span>
            )}
          </span>
          <span>Review</span>
        </NavLink>
        <NavLink to="/invoices" className={({ isActive }) => `mobile-tab${isActive ? " active" : ""}`}>
          <FontAwesomeIcon icon={faFileInvoiceDollar} />
          <span>Invoices</span>
        </NavLink>
        <button
          type="button"
          className={`mobile-tab${moreActive || moreOpen ? " active" : ""}`}
          aria-haspopup="dialog"
          aria-expanded={moreOpen}
          onClick={() => setMoreOpen((open) => !open)}
        >
          <FontAwesomeIcon icon={faEllipsis} />
          <span>More</span>
        </button>
      </nav>

      {moreOpen && (
        <div className="mobile-sheet-backdrop" onClick={() => setMoreOpen(false)}>
          <div
            className="mobile-sheet"
            role="dialog"
            aria-modal="true"
            aria-label="More"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mobile-sheet-grip" aria-hidden="true" />
            {MORE_LINKS.map(({ to, label, hint, icon }) => (
              <Link key={to} to={to} className="mobile-sheet-link" onClick={() => setMoreOpen(false)}>
                <span className="mobile-sheet-icon">
                  <FontAwesomeIcon icon={icon} />
                </span>
                <span className="mobile-sheet-text">
                  <strong>{label}</strong>
                  <small>{hint}</small>
                </span>
                <FontAwesomeIcon icon={faChevronRight} className="mobile-sheet-chevron" />
              </Link>
            ))}
          </div>
        </div>
      )}
    </>
  );
}
