import { Link } from "react-router-dom";

const tonAiLogo =
  "https://raw.githubusercontent.com/tungedng2710/tungedng2710.github.io/main/public/assets/images/logo.png";

export function Brand() {
  return (
    <Link to="/" className="flex items-center gap-2.5" aria-label="TonAI Data Studio home">
      <span className="grid size-8 place-items-center overflow-hidden rounded-lg bg-gradient-to-br from-white to-slate-100 p-1 shadow-sm ring-1 ring-slate-200">
        <img
          alt=""
          className="size-full object-contain"
          decoding="async"
          fetchPriority="high"
          src={tonAiLogo}
        />
      </span>
      <span>
        <span className="block text-sm font-bold tracking-tight text-slate-950">TonAI</span>
        <span className="block text-[9px] font-semibold tracking-[0.18em] text-slate-400 uppercase">
          Data Studio
        </span>
      </span>
    </Link>
  );
}
