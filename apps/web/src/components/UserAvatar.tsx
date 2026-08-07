import { useEffect, useState } from "react";

import { api } from "../api";
import type { PublicUser } from "../types";

export function UserAvatar({
  user,
  className = "size-8",
}: {
  user: Pick<PublicUser, "username" | "display_name" | "avatar_updated_at">;
  className?: string;
}) {
  const [failed, setFailed] = useState(false);
  const label = user.display_name || user.username;
  const initial = label.trim().charAt(0).toUpperCase() || "?";

  useEffect(() => setFailed(false), [user.avatar_updated_at]);

  if (user.avatar_updated_at && !failed) {
    return (
      <img
        alt=""
        className={`${className} shrink-0 rounded-full object-cover ring-1 ring-slate-200`}
        src={api.avatarUrl(user.username, user.avatar_updated_at)}
        onError={() => setFailed(true)}
      />
    );
  }

  return (
    <span
      className={`${className} grid shrink-0 place-items-center rounded-full bg-gradient-to-br from-indigo-100 to-cyan-100 font-semibold text-indigo-700 ring-1 ring-indigo-200`}
      aria-hidden="true"
    >
      {initial}
    </span>
  );
}
