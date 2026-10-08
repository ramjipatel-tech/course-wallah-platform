"use client";

import { useState, useEffect, useRef } from "react";
import Link from "next/link";
import { 
  Sparkles, 
  X, 
  Send, 
  Mic, 
  MicOff, 
  Bot, 
  User, 
  ArrowRight, 
  MessageSquare,
  BookOpen,
  Layers,
  HelpCircle
} from "lucide-react";
import { api } from "@/lib/api";
import { AIAction } from "@/lib/types";

interface Message {
  sender: "ai" | "user";
  text: string;
  actions?: AIAction[];
}

export function AIAssistant() {
  const [isOpen, setIsOpen] = useState(false);
  const [inputMessage, setInputMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [messages, setMessages] = useState<Message[]>([
    {
      sender: "ai",
      text: "Namaste! I am your **Course Wallah AI Learning Assistant**. How can I help you today?",
      actions: [
        { label: "My Batches", href: "/student" },
        { label: "Course Catalog", href: "/#courses" },
        { label: "Contact Support", href: "/contact" },
      ],
    },
  ]);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const recognitionRef = useRef<any>(null);

  // Initialize Web Speech API if supported
  useEffect(() => {
    if (typeof window !== "undefined") {
      const SpeechRecognition =
        (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
      if (SpeechRecognition) {
        const recognition = new SpeechRecognition();
        recognition.continuous = false;
        recognition.interimResults = false;
        recognition.lang = "en-IN"; // English (India) or multilingual

        recognition.onresult = (event: any) => {
          const transcript = event.results[0][0].transcript;
          if (transcript) {
            setInputMessage(transcript);
            handleSend(transcript);
          }
          setIsListening(false);
        };

        recognition.onerror = () => {
          setIsListening(false);
        };

        recognition.onend = () => {
          setIsListening(false);
        };

        recognitionRef.current = recognition;
      }
    }
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const toggleListening = () => {
    if (!recognitionRef.current) {
      alert("Voice input is not supported by your browser. Please use text input.");
      return;
    }

    if (isListening) {
      recognitionRef.current.stop();
      setIsListening(false);
    } else {
      try {
        recognitionRef.current.start();
        setIsListening(true);
      } catch (err) {
        setIsListening(false);
      }
    }
  };

  const handleSend = async (customText?: string) => {
    const textToSend = customText || inputMessage;
    if (!textToSend.trim() || loading) return;

    // Add user message
    const userMsg: Message = { sender: "user", text: textToSend.trim() };
    setMessages((prev) => [...prev, userMsg]);
    setInputMessage("");
    setLoading(true);

    try {
      const res = await api.queryAI(textToSend.trim());
      const aiMsg: Message = {
        sender: "ai",
        text: res.reply,
        actions: res.actions || [],
      };
      setMessages((prev) => [...prev, aiMsg]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          sender: "ai",
          text: "I'm having trouble connecting right now. Please explore courses directly from the catalog.",
          actions: [{ label: "Browse Catalog", href: "/#courses" }],
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      {/* Floating Trigger Button */}
      <div className="fixed bottom-6 right-6 z-40">
        {!isOpen && (
          <button
            onClick={() => setIsOpen(true)}
            className="group flex items-center gap-2.5 px-4 py-3 bg-gradient-to-r from-blue-600 via-indigo-600 to-cyan-600 hover:from-blue-500 hover:to-cyan-500 text-white font-bold text-xs sm:text-sm rounded-2xl shadow-xl shadow-blue-500/25 border border-white/20 transition-all hover:scale-105 active:scale-95"
            aria-label="Open AI Learning Assistant"
          >
            <span className="relative flex h-3 w-3">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-3 w-3 bg-cyan-500"></span>
            </span>
            <Sparkles className="w-4 h-4 text-cyan-200" />
            <span>Ask Wallah AI</span>
          </button>
        )}
      </div>

      {/* Floating Chat Modal */}
      {isOpen && (
        <div className="fixed bottom-6 right-4 sm:right-6 z-50 w-[92vw] sm:w-[400px] h-[540px] max-h-[85vh] bg-cw-surface border border-cw-border rounded-3xl shadow-2xl flex flex-col overflow-hidden animate-fade-in">
          {/* Header */}
          <div className="px-5 py-4 bg-cw-elevated/70 border-b border-cw-border flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-blue-600 to-cyan-500 flex items-center justify-center text-white shadow-md">
                <Sparkles className="w-5 h-5 text-white" />
              </div>
              <div>
                <h3 className="font-bold text-sm text-white flex items-center gap-1.5">
                  <span>Wallah AI Assistant</span>
                  <span className="text-[10px] px-1.5 py-0.2 rounded bg-blue-500/20 text-blue-400 border border-blue-500/30">
                    LIVE
                  </span>
                </h3>
                <p className="text-[11px] text-cw-muted">Course Wallah Academic Guide</p>
              </div>
            </div>

            <button
              onClick={() => setIsOpen(false)}
              className="p-1.5 rounded-lg text-cw-muted hover:text-white hover:bg-cw-surface transition-colors"
              aria-label="Close Assistant"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Messages Area */}
          <div className="flex-1 p-4 overflow-y-auto space-y-4 bg-cw-bg/50 text-xs">
            {messages.map((m, idx) => (
              <div
                key={idx}
                className={`flex gap-2.5 ${
                  m.sender === "user" ? "justify-end" : "justify-start"
                }`}
              >
                {m.sender === "ai" && (
                  <div className="w-7 h-7 rounded-lg bg-blue-600/20 border border-blue-500/30 flex items-center justify-center text-cw-primary flex-shrink-0 mt-0.5">
                    <Bot className="w-4 h-4" />
                  </div>
                )}

                <div
                  className={`max-w-[82%] p-3.5 rounded-2xl leading-relaxed space-y-2.5 ${
                    m.sender === "user"
                      ? "bg-cw-primary text-white font-medium rounded-tr-sm shadow-md"
                      : "bg-cw-surface border border-cw-border text-cw-text rounded-tl-sm shadow-sm"
                  }`}
                >
                  <p className="whitespace-pre-wrap">{m.text}</p>

                  {/* Action Link Chips */}
                  {m.actions && m.actions.length > 0 && (
                    <div className="flex flex-wrap gap-1.5 pt-1">
                      {m.actions.map((act, aIdx) => (
                        <Link
                          key={aIdx}
                          href={act.href}
                          onClick={() => setIsOpen(false)}
                          className="inline-flex items-center gap-1 px-2.5 py-1 bg-cw-elevated hover:bg-cw-surface-hover text-white border border-cw-border rounded-lg text-[11px] font-semibold transition-all hover:scale-105"
                        >
                          <span>{act.label}</span>
                          <ArrowRight className="w-3 h-3 text-cw-primary" />
                        </Link>
                      ))}
                    </div>
                  )}
                </div>

                {m.sender === "user" && (
                  <div className="w-7 h-7 rounded-lg bg-cw-elevated border border-cw-border flex items-center justify-center text-white flex-shrink-0 mt-0.5">
                    <User className="w-4 h-4" />
                  </div>
                )}
              </div>
            ))}

            {loading && (
              <div className="flex items-center gap-2 text-cw-muted italic text-[11px]">
                <Bot className="w-4 h-4 text-cw-primary animate-bounce" />
                <span>Wallah AI is finding answers...</span>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Quick Questions Suggestions */}
          <div className="px-3 py-2 bg-cw-surface border-t border-cw-border/60 flex items-center gap-1.5 overflow-x-auto no-scrollbar text-[11px]">
            <button
              onClick={() => handleSend("Show my enrolled batches")}
              className="px-2.5 py-1 rounded-full bg-cw-elevated hover:bg-cw-surface-hover border border-cw-border text-cw-text-secondary whitespace-nowrap transition-colors"
            >
              📚 My Batches
            </button>
            <button
              onClick={() => handleSend("Where is Digital Electronics?")}
              className="px-2.5 py-1 rounded-full bg-cw-elevated hover:bg-cw-surface-hover border border-cw-border text-cw-text-secondary whitespace-nowrap transition-colors"
            >
              🔍 Find Courses
            </button>
            <button
              onClick={() => handleSend("How to open lecture notes?")}
              className="px-2.5 py-1 rounded-full bg-cw-elevated hover:bg-cw-surface-hover border border-cw-border text-cw-text-secondary whitespace-nowrap transition-colors"
            >
              📄 Notes Access
            </button>
          </div>

          {/* Input & Voice Controls */}
          <div className="p-3 bg-cw-elevated/70 border-t border-cw-border">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                handleSend();
              }}
              className="flex items-center gap-2"
            >
              <input
                type="text"
                placeholder={isListening ? "Listening... Speak now" : "Ask anything about courses..."}
                value={inputMessage}
                onChange={(e) => setInputMessage(e.target.value)}
                className="flex-1 px-3.5 py-2.5 bg-cw-surface border border-cw-border rounded-xl text-xs text-white placeholder-cw-muted focus:outline-none focus:border-cw-primary transition-all"
              />

              {/* Voice Button */}
              <button
                type="button"
                onClick={toggleListening}
                className={`p-2.5 rounded-xl border transition-all ${
                  isListening
                    ? "bg-rose-600 text-white border-rose-500 animate-pulse"
                    : "bg-cw-surface hover:bg-cw-elevated text-cw-muted hover:text-white border-cw-border"
                }`}
                title="Voice Input (Speech Recognition)"
              >
                {isListening ? <Mic className="w-4 h-4" /> : <Mic className="w-4 h-4" />}
              </button>

              {/* Send Button */}
              <button
                type="submit"
                disabled={!inputMessage.trim() || loading}
                className="p-2.5 bg-cw-primary hover:bg-cw-primary-hover text-white rounded-xl disabled:opacity-30 disabled:pointer-events-none transition-all shadow-md"
                aria-label="Send Message"
              >
                <Send className="w-4 h-4" />
              </button>
            </form>
          </div>
        </div>
      )}
    </>
  );
}
