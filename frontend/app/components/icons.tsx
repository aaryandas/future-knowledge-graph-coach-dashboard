import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement>;

export function PanelIcon(props: IconProps) {
  return (
    <svg
      aria-hidden="true"
      fill="none"
      viewBox="0 0 20 20"
      stroke="currentColor"
      strokeWidth="1.5"
      {...props}
    >
      <rect x="2.75" y="3.25" width="14.5" height="13.5" rx="2.25" />
      <path d="M12.25 3.5v13" />
    </svg>
  );
}

export function SignOutIcon(props: IconProps) {
  return (
    <svg
      aria-hidden="true"
      fill="none"
      viewBox="0 0 20 20"
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth="1.5"
      {...props}
    >
      <path d="M8 3.5H5.25a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2H8" />
      <path d="M11.5 6.5 15 10l-3.5 3.5M7 10h8" />
    </svg>
  );
}

export function SendIcon(props: IconProps) {
  return (
    <svg
      aria-hidden="true"
      fill="none"
      viewBox="0 0 20 20"
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth="1.5"
      {...props}
    >
      <path d="m10 15.5.2-10M6.5 9l3.7-3.5L13.5 9" />
    </svg>
  );
}
