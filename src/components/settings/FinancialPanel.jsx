import { useMemo, useState } from "react";
import useSWR from "swr";
import InfoPanel from "./InfoPanel";
import {
  getSession, keys, fetchTimezone, saveTimezone, listTimezones, browserTimezone,
} from "../../services/settingsService";

function TimezoneField() {
  const userId = getSession().user_id;
  const { data, mutate } = useSWR(keys.timezone(userId), fetchTimezone);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const zones = useMemo(listTimezones, []);
  const detected = browserTimezone();

  if (!data) return null;

  const options = zones.includes(data.timezone) ? zones : [data.timezone, ...zones];
  const showDetectedHint = !data.isSet && detected && detected !== data.timezone && zones.includes(detected);

  const update = async (timezone) => {
    setSaving(true);
    setError("");
    try {
      await mutate(saveTimezone(userId, timezone), { revalidate: false });
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="settings-timezone">
      <label htmlFor="settings-timezone-select">Timezone</label>
      <select
        id="settings-timezone-select"
        className="settings-select"
        value={data.timezone}
        disabled={saving}
        onChange={(e) => update(e.target.value)}
      >
        {options.map((z) => (
          <option key={z} value={z}>{z.replace(/_/g, " ")}</option>
        ))}
      </select>
      <p className="settings-note">
        Loamy uses this to decide what &quot;today&quot;, &quot;this week&quot; and &quot;this month&quot; mean for you.
      </p>
      {showDetectedHint && (
        <p className="settings-note">
          Your browser is set to {detected.replace(/_/g, " ")}.{" "}
          <button type="button" className="settings-link" onClick={() => update(detected)}>
            Use that
          </button>
        </p>
      )}
      {error && <p className="settings-note" role="alert">{error}</p>}
    </div>
  );
}

export default function FinancialPanel() {
  return (
    <>
      <InfoPanel
        rows={[
          ["Base currency", "Naira (NGN)"],
          ["Foreign amounts", "Converted at the rate on the day, original amount kept"],
          ["Categories", "Learned from your confirmations, per account"],
        ]}
        note="Changing your base currency is not available yet."
      />
      <TimezoneField />
    </>
  );
}
