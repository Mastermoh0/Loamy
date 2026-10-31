import { useState } from "react";
import useSWR from "swr";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faTrash } from "@fortawesome/free-solid-svg-icons";
import { getSession, keys, fetchFacts, forgetFact } from "../../services/settingsService";

export default function DataPanel() {
  const { user_id: userId } = getSession();
  const { data: facts, error, isLoading, mutate } = useSWR(keys.facts(userId), fetchFacts);
  const [busyId, setBusyId] = useState(null);
  const [failure, setFailure] = useState("");

  const forget = async (id) => {
    setBusyId(id);
    setFailure("");
    try {
      await forgetFact(userId, id);
      await mutate((current) => (current || []).filter((f) => f.id !== id), { revalidate: false });
    } catch (e) {
      setFailure(e.message);
    } finally {
      setBusyId(null);
    }
  };

  return (
    <>
      <h3 className="settings-subhead">What Loamy has learned about you</h3>
      <p className="settings-lede">
        Loamy remembers details you share while resolving transactions, such as why a payment was made,
        so it can categorise and answer questions more accurately. Remove anything you don&apos;t want kept.
      </p>

      {failure && <p className="settings-error" role="alert">{failure}</p>}
      {isLoading && <p className="settings-muted">Loading...</p>}
      {error && <p className="settings-error" role="alert">Could not load what Loamy remembers.</p>}
      {facts && facts.length === 0 && <p className="settings-muted">Nothing remembered yet.</p>}

      <ul className="settings-facts">
        {(facts || []).map((f) => (
          <li key={f.id}>
            <div>
              <span>{f.fact}</span>
              {f.vendor && <small>{f.vendor}</small>}
            </div>
            <button
              type="button"
              className="settings-icon-btn"
              onClick={() => forget(f.id)}
              disabled={busyId === f.id}
              aria-label={`Forget: ${f.fact}`}
            >
              <FontAwesomeIcon icon={faTrash} />
            </button>
          </li>
        ))}
      </ul>
    </>
  );
}
