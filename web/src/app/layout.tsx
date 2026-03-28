import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "TRM — Thread Routing Module",
  description: "Live WebSocket view of TRM routing decisions",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="font-mono p-8">{children}</body>
    </html>
  );
}
