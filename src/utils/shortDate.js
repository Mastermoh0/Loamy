const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})/;

// "2026-11-02" -> "2 Nov" (the year is added only when it isn't the current one).
// ISO dates are built from their parts so a timezone offset can't shift the day.
export function shortDate(value) {
  if (!value) return "\u2014";
  const match = ISO_DATE.exec(String(value));
  const date = match
    ? new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]))
    : new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  const sameYear = date.getFullYear() === new Date().getFullYear();
  return date.toLocaleDateString(undefined, sameYear
    ? { day: "numeric", month: "short" }
    : { day: "numeric", month: "short", year: "numeric" });
}
