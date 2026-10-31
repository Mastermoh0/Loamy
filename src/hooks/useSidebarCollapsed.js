import { useCallback, useEffect, useState } from "react";

const STORAGE_KEY = "loamy_sidebar_collapsed";

function readStored() {
  try {
    return localStorage.getItem(STORAGE_KEY) === "true";
  } catch {
    return false;
  }
}

// Desktop sidebar open/closed state. Remembered across reloads and pages, and
// toggled with Ctrl/Cmd + B like most editors and chat apps.
export default function useSidebarCollapsed() {
  const [collapsed, setCollapsed] = useState(readStored);

  const toggle = useCallback(() => {
    setCollapsed((prev) => {
      const next = !prev;
      try {
        localStorage.setItem(STORAGE_KEY, String(next));
      } catch {
        /* storage unavailable: the toggle still works for this session */
      }
      return next;
    });
  }, []);

  useEffect(() => {
    const onKeyDown = (e) => {
      if ((e.ctrlKey || e.metaKey) && !e.shiftKey && !e.altKey && e.key.toLowerCase() === "b") {
        e.preventDefault();
        toggle();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [toggle]);

  return [collapsed, toggle];
}
