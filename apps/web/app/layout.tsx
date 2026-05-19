import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { Providers } from "./providers";
import { AnimatedBackground } from "./components/animated-background";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "MeetBuddy",
  description: "Privacy-first AI meeting intelligence",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className={inter.className}>
        <AnimatedBackground />
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
