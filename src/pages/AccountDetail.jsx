import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faArrowLeft, faArrowDown, faArrowUp, faPlus } from "@fortawesome/free-solid-svg-icons";
import ConnectBankModal from "../components/ConnectBankModal.jsx";
import BankLogo from "../components/BankLogo.jsx";
import Sidebar from "../components/Sidebar.jsx";
import TransactionDetailModal from "../components/TransactionDetailModal.jsx";
import { shortDate } from "../utils/shortDate.js";
import {
  fetchAccountTransactions,
  formatNaira,
  getSessionUserId,
} from "../services/bankService";
import "../InvoicesPage.css";

const TYPE_FILTERS = [
  { value: "", label: "All" },
  { value: "credit", label: "Income" },
  { value: "debit", label: "Expenses" },
];

const press = "transition-transform active:scale-[0.98]";

function formatDate(value) {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString("en-NG", { day: "numeric", month: "short", year: "numeric" });
}

function Metric({ label, value, tone = "text-gray-900", icon, iconTone }) {
  return (
    <div className={`flex min-w-0 items-center gap-3 rounded-3xl bg-white p-4 shadow-sm ${press}`}>
      {icon && (
        <span className={`flex size-10 shrink-0 items-center justify-center rounded-full ${iconTone}`}>
          <FontAwesomeIcon icon={icon} />
        </span>
      )}
      <div className="min-w-0">
        <p className="truncate text-xs text-gray-500">{label}</p>
        <p className={`truncate text-base font-semibold ${tone}`}>{value}</p>
      </div>
    </div>
  );
}

/*
 * AccountDetail - dashboard for one connected bank.
 * Fixed glass header, one scrolling content area, balance card, metrics and an
 * itemized list, all sourced from GET /api/v1/accounts/{account_id}/transactions.
 */
export default function AccountDetail() {
  const { accountId } = useParams();
  const [userId] = useState(getSessionUserId);
  const [typeFilter, setTypeFilter] = useState("");
  const [result, setResult] = useState({ key: null, data: null, error: null });
  const [modalOpen, setModalOpen] = useState(false);
  const [selectedTx, setSelectedTx] = useState(null);
  const closeDetail = useCallback(() => setSelectedTx(null), []);
  const navigate = useNavigate();
  const goBack = () => (window.history.length > 1 ? navigate(-1) : navigate("/dashboard"));

  // Loading is derived from whether the last response matches the current
  // request, so the effect only sets state from the async callback.
  const requestKey = `${accountId}|${typeFilter}`;
  const loading = result.key !== requestKey;
  const { data, error } = result;

  useEffect(() => {
    let cancelled = false;
    fetchAccountTransactions(userId, accountId, { type: typeFilter, limit: 200 }).then((res) => {
      if (cancelled) return;
      setResult((prev) =>
        res.status === "success"
          ? { key: requestKey, data: res.data, error: null }
          : {
              key: requestKey,
              data: prev.data,
              error: res.error === "no_session" ? "Please log in to view this account." : res.error,
            }
      );
    });
    return () => {
      cancelled = true;
    };
  }, [userId, accountId, typeFilter, requestKey]);

  const account = data?.account;
  const analytics = data?.analytics || {};
  const transactions = data?.transactions || [];
  const title = account?.nickname || account?.bank_name || "Bank account";

  return (
    <div className="flex h-full min-h-0 flex-col bg-canvas min-[769px]:ml-60">
      <Sidebar />

      <header className="z-10 flex shrink-0 items-center gap-2 bg-white/80 px-3 pb-2 pt-[calc(env(safe-area-inset-top)+0.5rem)] shadow-sm backdrop-blur-md">
        <button
          type="button"
          onClick={goBack}
          aria-label="Go back"
          className={`flex size-11 shrink-0 items-center justify-center rounded-2xl text-loamy-700 ${press}`}
        >
          <FontAwesomeIcon icon={faArrowLeft} />
        </button>
        <BankLogo
          name={account?.bank_name || account?.nickname}
          slug={account?.bank_slug}
          backendLogo={account?.logo}
          imgClassName="size-10 rounded-xl object-contain"
          className="size-10 rounded-xl"
          size={40}
        />
        <div className="min-w-0 flex-1">
          <h1 className="truncate text-base font-semibold text-gray-900">{title}</h1>
          <p className="flex items-center gap-2 truncate text-xs text-gray-500">
            <span className="truncate">
              {account?.bank_name}
              {account?.account_tail ? ` •••• ${account.account_tail}` : ""}
            </span>
            {account?.status && (
              <span className="shrink-0 rounded-full bg-loamy-100 px-2 py-0.5 text-[11px] font-medium capitalize text-loamy-700">
                {account.status}
              </span>
            )}
          </p>
        </div>
        <button
          type="button"
          onClick={() => setModalOpen(true)}
          aria-label="Connect bank"
          className={`flex min-h-11 shrink-0 items-center justify-center gap-2 rounded-2xl bg-loamy-700 px-3 text-sm font-medium text-white shadow-sm ${press}`}
        >
          <FontAwesomeIcon icon={faPlus} />
          <span className="max-[420px]:sr-only">Connect bank</span>
        </button>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto overscroll-none px-4 pb-6 pt-4">
        <div className="mx-auto flex max-w-3xl flex-col gap-4">
          {error && (
            <div role="alert" className="rounded-2xl bg-red-50 p-4 text-sm text-red-700">
              {error}
            </div>
          )}

          {!error && (
            <>
              <section
                aria-label="Total balance"
                className={`rounded-3xl bg-loamy-700 p-5 text-white shadow-sm ${press}`}
              >
                <p className="text-sm text-white/80">Total balance</p>
                <p className="mt-1 truncate text-3xl font-semibold">
                  {loading && !data ? "…" : formatNaira(analytics.balance)}
                </p>
                <p className="mt-3 text-xs text-white/80">
                  {analytics.last_activity
                    ? `Last activity ${formatDate(analytics.last_activity)}`
                    : "Balance updates from your latest bank alert"}
                </p>
              </section>

              <section aria-label="Account metrics" className="grid grid-cols-2 gap-3">
                <Metric
                  label="Income"
                  value={formatNaira(analytics.total_credits)}
                  tone="text-loamy-700"
                  icon={faArrowDown}
                  iconTone="bg-loamy-100 text-loamy-700"
                />
                <Metric
                  label="Expenses"
                  value={formatNaira(analytics.total_debits)}
                  tone="text-red-600"
                  icon={faArrowUp}
                  iconTone="bg-red-50 text-red-600"
                />
                <Metric
                  label="Net flow"
                  value={formatNaira(analytics.net_flow)}
                  tone={analytics.net_flow < 0 ? "text-red-600" : "text-loamy-700"}
                />
                <Metric label="Transactions" value={analytics.transaction_count ?? 0} />
              </section>

              <section aria-labelledby="ad-tx-title" className="rounded-3xl bg-white p-4 shadow-sm">
                <div className="mb-3 flex flex-col gap-3">
                  <h2 id="ad-tx-title" className="text-lg font-semibold text-gray-900">
                    Transactions
                  </h2>
                  <div
                    role="group"
                    aria-label="Filter by type"
                    className="flex gap-1 rounded-2xl bg-gray-100 p-1"
                  >
                    {TYPE_FILTERS.map((f) => {
                      const active = typeFilter === f.value;
                      return (
                        <button
                          key={f.value || "all"}
                          type="button"
                          aria-pressed={active}
                          onClick={() => setTypeFilter(f.value)}
                          className={`min-h-11 flex-1 rounded-xl px-3 text-sm font-medium ${press} ${
                            active ? "bg-white text-loamy-700 shadow-sm" : "text-gray-500"
                          }`}
                        >
                          {f.label}
                        </button>
                      );
                    })}
                  </div>
                </div>

                {loading ? (
                  <p className="py-8 text-center text-sm text-gray-500">Loading transactions…</p>
                ) : transactions.length === 0 ? (
                  <p className="py-8 text-center text-sm text-gray-500">
                    No transactions yet. New alerts from this bank will appear here after the next sync.
                  </p>
                ) : (
                  <>
                    <ul className="flex flex-col min-[769px]:hidden">
                      {transactions.map((tx) => {
                        const isCredit = tx.type === "credit";
                        const description = tx.merchant || tx.description || tx.raw_subject || "Transaction";
                        return (
                          <li key={tx.id} className="border-t border-gray-100 first:border-t-0">
                            <button
                              type="button"
                              onClick={() => setSelectedTx(tx)}
                              aria-label={`View details: ${description}`}
                              className={`grid min-h-14 w-full grid-cols-[1fr_auto] items-center gap-x-3 gap-y-1 rounded-2xl px-1 py-3 text-left ${press} active:bg-gray-50`}
                            >
                              <span className="truncate text-sm font-medium text-gray-900">{description}</span>
                              <span
                                className={`text-sm font-semibold ${isCredit ? "text-loamy-700" : "text-red-600"}`}
                              >
                                {isCredit ? "+" : "−"}
                                {formatNaira(tx.amount ?? tx.transaction_amount ?? 0)}
                              </span>
                              <span className="truncate text-xs text-gray-500">
                                {tx.category || "Uncategorized"}
                              </span>
                              <span className="text-xs text-gray-500">{shortDate(tx.date)}</span>
                            </button>
                          </li>
                        );
                      })}
                    </ul>

                    <div className="hidden overflow-x-auto min-[769px]:block">
                      <table className="w-full text-left text-sm">
                        <thead>
                          <tr className="text-xs text-gray-500">
                            <th scope="col" className="px-3 py-2 font-medium">Date</th>
                            <th scope="col" className="px-3 py-2 font-medium">Description</th>
                            <th scope="col" className="px-3 py-2 font-medium">Category</th>
                            <th scope="col" className="px-3 py-2 text-right font-medium">Amount</th>
                            <th scope="col" className="px-3 py-2 text-right font-medium">Balance</th>
                          </tr>
                        </thead>
                        <tbody>
                          {transactions.map((tx) => {
                            const isCredit = tx.type === "credit";
                            return (
                              <tr
                                key={tx.id}
                                tabIndex={0}
                                onClick={() => setSelectedTx(tx)}
                                onKeyDown={(e) => {
                                  if (e.key === "Enter" || e.key === " ") {
                                    e.preventDefault();
                                    setSelectedTx(tx);
                                  }
                                }}
                                className="cursor-pointer border-t border-gray-100 hover:bg-gray-50"
                              >
                                <td className="whitespace-nowrap px-3 py-3">{formatDate(tx.date)}</td>
                                <td className="px-3 py-3">
                                  {tx.merchant || tx.description || tx.raw_subject || "Transaction"}
                                </td>
                                <td className="px-3 py-3">
                                  <span className="rounded-full bg-gray-100 px-2 py-1 text-xs text-gray-600">
                                    {tx.category || "Uncategorized"}
                                  </span>
                                </td>
                                <td
                                  className={`whitespace-nowrap px-3 py-3 text-right font-semibold ${
                                    isCredit ? "text-loamy-700" : "text-red-600"
                                  }`}
                                >
                                  {isCredit ? "+" : "−"}
                                  {formatNaira(tx.amount ?? tx.transaction_amount ?? 0)}
                                </td>
                                <td className="whitespace-nowrap px-3 py-3 text-right text-gray-500">
                                  {formatNaira(tx.balance_after ?? tx.balance ?? tx.running_balance ?? 0)}
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </>
                )}
              </section>
            </>
          )}
        </div>
      </div>

      <TransactionDetailModal
        tx={selectedTx}
        bank={account ? { name: account.bank_name || account.nickname, slug: account.bank_slug, logo: account.logo } : null}
        onClose={closeDetail}
      />

      <ConnectBankModal
        isOpen={modalOpen}
        onClose={() => setModalOpen(false)}
        userId={userId}
      />
    </div>
  );
}
