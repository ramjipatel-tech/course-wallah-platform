import "./globals.css";
import type { Metadata } from "next";
import { Navbar } from "@/components/navigation/Navbar";
import { Footer } from "@/components/navigation/Footer";
import { AIAssistant } from "@/components/ai/AIAssistant";

export const metadata: Metadata = {
  title: "Course Wallah — Dynamic Student Learning Platform",
  description: "Next-Generation Engineering Education Platform with Interactive Streams and Study Notes",
  icons: {
    icon: "/logo.png",
    shortcut: "/logo.png",
    apple: "/logo.png",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark scroll-smooth">
      <body className="bg-cw-bg text-cw-text min-h-screen flex flex-col antialiased selection:bg-cw-primary/30 selection:text-white">
        <Navbar />
        <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8">
          {children}
        </main>
        <AIAssistant />
        <Footer />
      </body>
    </html>
  );
}
