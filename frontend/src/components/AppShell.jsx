import { NavLink } from "react-router-dom";

/** Project mark. Deliberately not any issuer's trademark — an abstract arbitration
 *  glyph: two opposing parties and the boundary the scorecard draws between them. */
function Mark() {
  return (
    <svg width="26" height="26" viewBox="0 0 26 26" role="img" aria-label="Dispute Resolution">
      <rect width="26" height="26" rx="6" fill="#006FCF" />
      <path d="M5.5 18.5 L11 7.5" stroke="#fff" strokeWidth="2" strokeLinecap="round" opacity="0.95" />
      <path d="M20.5 18.5 L15 7.5" stroke="#9FD6FF" strokeWidth="2" strokeLinecap="round" />
      <path d="M13 5.5 L13 20.5" stroke="#fff" strokeWidth="1.5" strokeLinecap="round" opacity="0.5" />
      <circle cx="13" cy="5.5" r="1.9" fill="#fff" />
    </svg>
  );
}

export default function AppShell({ children }) {
  return (
    <div className="shell">
      <header className="topbar">
        <div className="topbar__inner">
          <div className="brand">
            <Mark />
            <div>
              <div className="brand__name">Dispute Resolution</div>
              <div className="brand__sub">Issuer Arbitration Console</div>
            </div>
          </div>
          <nav className="nav">
            <NavLink to="/" end className={({ isActive }) => `nav__link${isActive ? " is-active" : ""}`}>
              Dashboard
            </NavLink>
            <NavLink to="/cases" className={({ isActive }) => `nav__link${isActive ? " is-active" : ""}`}>
              Cases
            </NavLink>
          </nav>
        </div>
      </header>
      <main className="page">{children}</main>
    </div>
  );
}
