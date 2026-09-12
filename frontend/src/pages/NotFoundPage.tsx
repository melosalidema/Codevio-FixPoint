import { Link } from "react-router-dom";

import { Panel } from "../components/Ui";

export function NotFoundPage() {
  return (
    <Panel title="Not found">
      <div className="py-8 text-center">
        <p className="text-slate-300">That page does not exist.</p>
        <Link to="/" className="btn-primary mt-4 inline-flex">
          Back to Run Console
        </Link>
      </div>
    </Panel>
  );
}
