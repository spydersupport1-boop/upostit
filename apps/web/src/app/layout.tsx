import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Attendance SaaS — Enterprise Dashboard",
  description: "Multi-tenant attendance and workforce management platform with fraud shield",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
