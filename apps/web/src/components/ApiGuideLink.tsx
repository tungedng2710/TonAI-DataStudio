import { BookOpenText } from "lucide-react";
import { Link } from "react-router-dom";

export function ApiGuideLink() {
  return (
    <Link
      aria-label="API guide"
      className="header-action"
      to="/docs/api"
    >
      <BookOpenText className="size-4" />
      <span className="hidden sm:inline">API guide</span>
    </Link>
  );
}
