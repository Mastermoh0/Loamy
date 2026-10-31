// Read-only panel for sections that describe how Loamy behaves today but have
// no saved preference behind them yet.
export default function InfoPanel({ rows, note }) {
  return (
    <>
      <dl className="settings-fields">
        {rows.map(([label, value]) => (
          <div key={label}><dt>{label}</dt><dd>{value}</dd></div>
        ))}
      </dl>
      <p className="settings-note">{note}</p>
    </>
  );
}
