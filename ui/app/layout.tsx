import type { Metadata } from "next";
import Nav from "@/components/Nav";
import "./globals.css";

export const metadata: Metadata = {
  title: "SKYVAULT",
  description: "What happened in a SKYVAULT run, why, and what to change before reality.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header className="top">
          <a href="/" className="brand">
            SKYVAULT
          </a>
          <Nav />
        </header>
        <main className="page">{children}</main>
      </body>
    </html>
  );
}
