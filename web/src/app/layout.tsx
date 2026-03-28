import type { Metadata } from "next";

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
      <body style={{ fontFamily: "monospace", padding: "2rem" }}>{children}</body>
    </html>
  );
}
