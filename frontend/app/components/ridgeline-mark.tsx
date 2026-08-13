import { cx } from "@/lib/theme";

export function RidgelineMark({ className }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cx(
        "grid shrink-0 place-items-center rounded-full border-[1.5px] border-foreground text-[15px] font-light leading-none",
        className,
      )}
    >
      ◎
    </span>
  );
}
