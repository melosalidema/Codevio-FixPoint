import { Link } from "react-router-dom";

import { Panel } from "../components/Ui";

export function NotFoundPage() {
  return (
    <Panel title="Not found">
      <p className="py-4 text-center text-sm text-slate-400">This page does not exist in the demo store.</p>
      <div className="text-center">
        <Link to="/" className="btn-primary">
          Back to shop
        </Link>
      </div>
    </Panel>
  );
}
