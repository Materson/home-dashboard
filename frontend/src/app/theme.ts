/**
 * The look: Inter, soft rounded white cards on a light grey page (see
 * global.css and AppShell), gentle shadows, calm tables and modals.
 * Component defaults live here so pages stay plain Mantine.
 */
import {
  Badge,
  Button,
  Card,
  createTheme,
  Drawer,
  Menu,
  Modal,
  Notification,
  Paper,
  Popover,
  rem,
  SegmentedControl,
  Table,
  Tooltip,
} from "@mantine/core";

const FONT = "'Inter Variable', Inter, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif";
const OVERLAY = { backgroundOpacity: 0.35, blur: 3 };

export const theme = createTheme({
  primaryColor: "indigo",
  primaryShade: { light: 6, dark: 5 },
  fontFamily: FONT,
  headings: {
    fontFamily: FONT,
    fontWeight: "650",
    sizes: {
      h1: { fontSize: rem(30), lineHeight: "1.2" },
      h2: { fontSize: rem(24), lineHeight: "1.25" },
      h3: { fontSize: rem(19), lineHeight: "1.3" },
      h4: { fontSize: rem(16), lineHeight: "1.35" },
      h5: { fontSize: rem(14), lineHeight: "1.4" },
    },
  },
  defaultRadius: "md",
  radius: { xs: rem(4), sm: rem(6), md: rem(8), lg: rem(12), xl: rem(16) },
  shadows: {
    xs: "0 1px 2px rgba(16, 24, 40, 0.05)",
    sm: "0 1px 3px rgba(16, 24, 40, 0.08), 0 1px 2px rgba(16, 24, 40, 0.04)",
    md: "0 6px 16px -4px rgba(16, 24, 40, 0.10), 0 2px 4px -2px rgba(16, 24, 40, 0.05)",
    lg: "0 14px 28px -6px rgba(16, 24, 40, 0.12), 0 4px 8px -4px rgba(16, 24, 40, 0.05)",
    xl: "0 24px 48px -12px rgba(16, 24, 40, 0.20)",
  },
  cursorType: "pointer",
  components: {
    Paper: Paper.extend({ defaultProps: { radius: "lg", shadow: "xs" } }),
    Card: Card.extend({ defaultProps: { radius: "lg", shadow: "xs", withBorder: true } }),
    Modal: Modal.extend({ defaultProps: { radius: "lg", overlayProps: OVERLAY } }),
    Drawer: Drawer.extend({ defaultProps: { overlayProps: OVERLAY } }),
    Menu: Menu.extend({ defaultProps: { radius: "md", shadow: "md" } }),
    Popover: Popover.extend({ defaultProps: { radius: "md", shadow: "md" } }),
    Tooltip: Tooltip.extend({ defaultProps: { radius: "sm", openDelay: 150 } }),
    Notification: Notification.extend({ defaultProps: { radius: "md" } }),
    SegmentedControl: SegmentedControl.extend({ defaultProps: { radius: "md" } }),
    Table: Table.extend({ defaultProps: { highlightOnHover: true } }),
    Button: Button.extend({ styles: { root: { fontWeight: 600 } } }),
    Badge: Badge.extend({ styles: { root: { textTransform: "none", fontWeight: 600, letterSpacing: 0 } } }),
  },
});
