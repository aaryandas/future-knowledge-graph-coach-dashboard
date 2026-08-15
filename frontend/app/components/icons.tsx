import {
  ControlSlider,
  DotsGrid3x3,
  EditPencil,
  GraphDown,
  Gym,
  LogOut,
  Page,
  Plus,
  PrecisionTool,
  SendDiagonal,
  ShieldCheck,
  Star,
  Trash,
  User,
  ViewColumns2,
  Walking,
  Xmark,
} from "iconoir-react";
import type { ComponentType, SVGProps } from "react";

export type IconProps = SVGProps<SVGSVGElement>;

function createIcon(Icon: ComponentType<IconProps>) {
  return function IconoirCompatibilityIcon(props: IconProps) {
    return <Icon aria-hidden="true" {...props} />;
  };
}

export const PersonIcon = createIcon(User);
export const KneeIcon = createIcon(Walking);
export const DumbbellIcon = createIcon(Gym);
export const TrendIcon = createIcon(GraphDown);
export const GoalIcon = createIcon(PrecisionTool);
export const StarIcon = createIcon(Star);
export const GripIcon = createIcon(DotsGrid3x3);
export const PencilIcon = createIcon(EditPencil);
export const TrashIcon = createIcon(Trash);
export const PlusIcon = createIcon(Plus);
export const AdjustIcon = createIcon(ControlSlider);
export const ExplainIcon = createIcon(Page);
export const ShieldIcon = createIcon(ShieldCheck);
export const CloseIcon = createIcon(Xmark);
export const PanelIcon = createIcon(ViewColumns2);
export const SignOutIcon = createIcon(LogOut);
export const SendIcon = createIcon(SendDiagonal);
