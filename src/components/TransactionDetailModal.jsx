import { useEffect, useRef } from "react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faXmark } from "@fortawesome/free-solid-svg-icons";
import BankLogo from "./BankLogo.jsx";
import { formatNaira } from "../services/bankService.js";
import "./TransactionDetailModal.css";

const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})/;

function longDate(value) {
  if (!value) return "";
  const match = ISO_DATE.exec(String(value));
  const date = match
    ? new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]))
    : new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "long", year: "numeric" });
}

/*
 * TransactionDetailModal - small popup with the full, untruncated detail of
 * one transaction. `bank` is { name, slug, logo }.
 */
export default function TransactionDetailModal({ tx, bank, onClose }) {
  const closeRef = useRef(null);

  useEffect(() => {
    if (!tx) return undefined;
    const previouslyFocused = document.activeElement;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeRef.current?.focus();
    const onKeyDown = (e) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", onKeyDown);
      previouslyFocused?.focus?.();
    };
  }, [tx, onClose]);

  if (!tx) return null;

  const credit = tx.type === "credit";
  const description = tx.merchant || tx.description || tx.raw_subject || "Transaction";
  const amount = tx.amount ?? tx.transaction_amount ?? 0;
  const balance = tx.balance_after ?? tx.balance ?? tx.running_balance;
  const originalText = tx.raw_subject && tx.raw_subject !== description ? tx.raw_subject : "";
  const reference = tx.reference || tx.transaction_reference || tx.id;

  const rows = [
    { label: "Bank", value: bank?.name, node: bank?.name && (
      <span className="tx-modal-bank">
        <BankLogo name={bank.name} slug={bank.slug} backendLogo={bank.logo} size={20} />
        {bank.name}
      </span>
    ) },
    { label: "Date", value: longDate(tx.date) },
    { label: "Category", value: tx.category || "Uncategorized", node: <span className="tx-modal-chip">{tx.category || "Uncategorized"}</span> },
    { label: "Type", value: credit ? "Money in" : "Money out" },
    { label: "Balance after", value: balance !== undefined && balance !== null ? formatNaira(balance) : "" },
    { label: "Original text", value: originalText },
    { label: "Reference", value: reference ? String(reference) : "", mono: true },
  ].filter((row) => row.value);

  return (
    <div className="tx-modal-backdrop" onClick={onClose}>
      <div
        className="tx-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="tx-modal-title"
        onClick={(e) => e.stopPropagation()}
      >
        <button ref={closeRef} type="button" className="tx-modal-close" onClick={onClose} aria-label="Close transaction details">
          <FontAwesomeIcon icon={faXmark} />
        </button>
        <p className="tx-modal-kicker">{credit ? "Money in" : "Money out"}</p>
        <p className={`tx-modal-amount ${credit ? "tx-modal-positive" : "tx-modal-negative"}`}>
          {credit ? "+" : "−"}{formatNaira(amount)}
        </p>
        <h2 id="tx-modal-title" className="tx-modal-title">{description}</h2>
        <dl className="tx-modal-rows">
          {rows.map((row) => (
            <div className="tx-modal-row" key={row.label}>
              <dt>{row.label}</dt>
              <dd className={row.mono ? "tx-modal-mono" : undefined}>{row.node || row.value}</dd>
            </div>
          ))}
        </dl>
      </div>
    </div>
  );
}
