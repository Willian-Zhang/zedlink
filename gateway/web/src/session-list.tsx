import React from "react";
import { createRoot } from "react-dom/client";
import { flushSync } from "react-dom";

type Session = {
  id: string;
  title: string;
  agent: string;
  status: string;
  running: boolean;
  attention: boolean;
  active: boolean;
  pinned: boolean;
  updated: boolean;
  tag: string;
  project: string;
  seenAt: number;
};

type SessionGroup = { label: string; sessions: Session[] };
type SessionListProps = {
  groups: SessionGroup[];
  emptyMessage: string;
  canClear: boolean;
  onSelect: (id: string) => void;
  onPin: (id: string) => void;
  onClear: () => void;
};

function SessionList({ groups, emptyMessage, canClear, onSelect, onPin, onClear }: SessionListProps) {
  if (!groups.length) return <div className="sessions-empty"><p>{emptyMessage}</p>{canClear &&
    <button type="button" onClick={onClear}>Clear search and filters</button>}</div>;
  return <>{groups.map((group) => <React.Fragment key={group.label}>
    <h3 className="session-group">{group.label} · {group.sessions.length}</h3>
    {group.sessions.map((session) => <div className="session-row" key={session.id}>
      <button type="button" data-thread-id={session.id}
        className={`thread-item ${session.active ? "active" : ""} ${session.running ? "running" : ""} ${session.attention ? "error" : ""}`}
        aria-current={session.active ? "page" : undefined}
        aria-label={`${session.title}, ${session.agent}${session.project ? `, ${session.project}` : ""}, ${session.status}${session.updated ? ", new activity" : ""}`}
        onClick={() => onSelect(session.id)}>
        <span className="thread-badge">{session.agent}</span>
        <span className={`thread-status ${session.running ? "busy" : ""} ${session.attention ? "error" : ""}`}>
          {session.running && <span className="thread-progress" aria-hidden="true"><i/><i/><i/></span>}
          <span>{session.status}</span>
        </span>
        <strong>{session.title}</strong>
        {session.project && <small className="session-project">{session.project}</small>}
        {session.tag && <small className="session-tag">{session.tag}</small>}
        {session.updated && <small>New activity</small>}
      </button>
      <button type="button" className="session-pin" aria-label={`${session.pinned ? "Unpin" : "Pin"} ${session.title}`}
        aria-pressed={session.pinned} title={session.pinned ? "Unpin session" : "Pin session"} onClick={() => onPin(session.id)}>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M8 3h8l-1.2 6 3.2 3v2H6v-2l3.2-3L8 3Z"/><path d="M12 14v7"/></svg>
      </button>
    </div>)}
  </React.Fragment>)}</>;
}

const container = document.getElementById("thread-list");
if (!container) throw new Error("Session list mount is missing");
const root = createRoot(container);

declare global {
  interface Window {
    ZedLinkSessions: { render: (props: SessionListProps) => void };
  }
}

window.ZedLinkSessions = {
  render(props) {
    // Session updates arrive from the existing native-thread controller. Commit before
    // it restores sidebar scroll position or reads a newly selected row.
    flushSync(() => root.render(<SessionList {...props}/>));
  },
};
