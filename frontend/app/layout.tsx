import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "VeinCAD CNC",
  description: "Stone vein tracing and DXF export workspace",
  icons: {
    icon: "/stone-logo.png",
    shortcut: "/stone-logo.png",
    apple: "/stone-logo.png",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
