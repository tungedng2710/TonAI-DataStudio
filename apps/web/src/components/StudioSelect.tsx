import { Check, ChevronDown } from "lucide-react";
import {
  type KeyboardEvent,
  type ReactNode,
  useEffect,
  useId,
  useRef,
  useState,
} from "react";

export type StudioSelectOption = {
  value: string;
  label: string;
  description?: string;
};

export function StudioSelect({
  value,
  options,
  onChange,
  ariaLabel,
  label,
  leadingIcon,
  className = "",
  disabled = false,
}: {
  value: string;
  options: StudioSelectOption[];
  onChange: (value: string) => void;
  ariaLabel: string;
  label?: string;
  leadingIcon?: ReactNode;
  className?: string;
  disabled?: boolean;
}) {
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const listboxId = useId();
  const selectedIndex = Math.max(
    0,
    options.findIndex((option) => option.value === value),
  );
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(selectedIndex);
  const selected = options.find((option) => option.value === value) ?? options[0];

  useEffect(() => {
    if (!open) setActiveIndex(selectedIndex);
  }, [open, selectedIndex]);

  useEffect(() => {
    if (!open) return;

    const closeOnOutsidePointer = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", closeOnOutsidePointer);
    return () => document.removeEventListener("pointerdown", closeOnOutsidePointer);
  }, [open]);

  const choose = (index: number) => {
    const option = options[index];
    if (!option) return;
    onChange(option.value);
    setOpen(false);
    triggerRef.current?.focus();
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (!open) {
        setOpen(true);
        setActiveIndex(selectedIndex);
        return;
      }
      const direction = event.key === "ArrowDown" ? 1 : -1;
      setActiveIndex((current) => (current + direction + options.length) % options.length);
    } else if (event.key === "Home" && open) {
      event.preventDefault();
      setActiveIndex(0);
    } else if (event.key === "End" && open) {
      event.preventDefault();
      setActiveIndex(options.length - 1);
    } else if ((event.key === "Enter" || event.key === " ") && open) {
      event.preventDefault();
      choose(activeIndex);
    } else if (event.key === "Escape" && open) {
      event.preventDefault();
      setOpen(false);
    }
  };

  if (!selected) return null;

  return (
    <div className={`studio-select ${open ? "studio-select-open" : ""} ${className}`} ref={rootRef}>
      <button
        aria-activedescendant={open ? `${listboxId}-option-${activeIndex}` : undefined}
        aria-controls={listboxId}
        aria-expanded={open}
        aria-haspopup="listbox"
        aria-label={ariaLabel}
        className="studio-select-trigger"
        disabled={disabled}
        onBlur={() => {
          requestAnimationFrame(() => {
            if (!rootRef.current?.contains(document.activeElement)) setOpen(false);
          });
        }}
        onClick={() => {
          setActiveIndex(selectedIndex);
          setOpen((current) => !current);
        }}
        onKeyDown={handleKeyDown}
        ref={triggerRef}
        role="combobox"
        type="button"
      >
        {leadingIcon ? <span className="studio-select-leading">{leadingIcon}</span> : null}
        {label ? <span className="studio-select-context">{label}</span> : null}
        <span className={`studio-select-value ${value ? "" : "text-slate-400"}`} title={selected.label}>
          {selected.label}
        </span>
        <ChevronDown className="studio-select-chevron" aria-hidden="true" />
      </button>

      {open ? (
        <div className="studio-select-menu" id={listboxId} role="listbox" aria-label={ariaLabel}>
          {options.map((option, index) => {
            const isSelected = option.value === value;
            const isActive = index === activeIndex;
            return (
              <button
                aria-selected={isSelected}
                className={`studio-select-option ${isActive ? "studio-select-option-active" : ""}`}
                id={`${listboxId}-option-${index}`}
                key={option.value}
                onClick={() => choose(index)}
                onMouseEnter={() => setActiveIndex(index)}
                role="option"
                tabIndex={-1}
                type="button"
              >
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-semibold text-slate-800">{option.label}</span>
                  {option.description ? (
                    <span className="mt-0.5 block text-xs leading-4 text-slate-500">
                      {option.description}
                    </span>
                  ) : null}
                </span>
                <span className={`studio-select-check ${isSelected ? "studio-select-check-active" : ""}`}>
                  <Check className="size-3.5" aria-hidden="true" />
                </span>
              </button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
