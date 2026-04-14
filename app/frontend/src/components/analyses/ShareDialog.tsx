import { useState, useEffect, useRef, useCallback } from "react";
import { Share2, ChevronDown, Search, X } from "lucide-react";
import { api } from "../../lib/api";
import type { Collaborator } from "../../lib/types";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Badge } from "../ui/badge";
import {
  Dialog,
  DialogTrigger,
  DialogContent,
  DialogTitle,
} from "../ui/dialog";

interface ShareDialogProps {
  analysisId: string;
  isPublished: boolean;
  ownerEmail: string;
  collaborators: Collaborator[];
  onUpdate: () => void;
}

interface UserResult {
  email: string;
  display_name: string;
}

export function ShareDialog({
  analysisId,
  isPublished,
  ownerEmail,
  collaborators,
  onUpdate,
}: ShareDialogProps) {
  const [published, setPublished] = useState(isPublished);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<UserResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [showResults, setShowResults] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const searchContainerRef = useRef<HTMLDivElement>(null);

  // Sync published state when prop changes
  useEffect(() => setPublished(isPublished), [isPublished]);

  // Close results dropdown on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (
        searchContainerRef.current &&
        !searchContainerRef.current.contains(e.target as Node)
      ) {
        setShowResults(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const doSearch = useCallback(async (q: string) => {
    if (q.length < 2) {
      setSearchResults([]);
      setShowResults(false);
      return;
    }
    setSearching(true);
    try {
      const data = await api.get<{ users: UserResult[] }>(
        `/users/search?q=${encodeURIComponent(q)}`,
      );
      setSearchResults(data.users);
      setShowResults(true);
    } catch {
      setSearchResults([]);
    } finally {
      setSearching(false);
    }
  }, []);

  const handleSearchChange = (value: string) => {
    setSearchQuery(value);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => doSearch(value), 300);
  };

  const togglePublish = async () => {
    const next = !published;
    setPublished(next);
    try {
      if (next) {
        await api.post(`/analyses/${analysisId}/publish`);
      } else {
        await api.post(`/analyses/${analysisId}/unpublish`);
      }
      onUpdate();
    } catch {
      setPublished(!next); // revert on error
    }
  };

  const addCollaborator = async (email: string) => {
    setSearchQuery("");
    setSearchResults([]);
    setShowResults(false);
    await api.post(`/analyses/${analysisId}/collaborators`, {
      user_email: email,
      role: "viewer",
    });
    onUpdate();
  };

  const removeCollaborator = async (email: string) => {
    await api.delete(`/analyses/${analysisId}/collaborators/${encodeURIComponent(email)}`);
    onUpdate();
  };

  // Filter out owner and existing collaborators from search results
  const existingEmails = new Set([
    ownerEmail,
    ...collaborators.map((c) => c.user_email),
  ]);
  const filteredResults = searchResults.filter(
    (u) => !existingEmails.has(u.email),
  );

  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          <Share2 className="h-3.5 w-3.5 mr-1" />
          Share
          <ChevronDown className="h-3 w-3 ml-0.5 opacity-60" />
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogTitle>Share Analysis</DialogTitle>

        <div className="mt-4 space-y-4">
          {/* Published toggle */}
          <label className="flex items-center gap-2 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={published}
              onChange={togglePublish}
              className="h-4 w-4 rounded border-border accent-primary"
            />
            <span className="text-sm">Published (visible to all users)</span>
          </label>

          {/* User search */}
          <div ref={searchContainerRef} className="relative">
            <div className="relative">
              <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Search users by email..."
                value={searchQuery}
                onChange={(e) => handleSearchChange(e.target.value)}
                onFocus={() => {
                  if (searchResults.length > 0) setShowResults(true);
                }}
                className="pl-9"
              />
            </div>

            {/* Search results dropdown */}
            {showResults && filteredResults.length > 0 && (
              <div className="absolute z-10 mt-1 w-full rounded-md border border-border bg-background shadow-md max-h-40 overflow-y-auto">
                {filteredResults.map((u) => (
                  <button
                    key={u.email}
                    onClick={() => addCollaborator(u.email)}
                    className="flex w-full items-center gap-2 px-3 py-2 text-sm hover:bg-muted text-left"
                  >
                    <span className="truncate">{u.email}</span>
                    {u.display_name && u.display_name !== u.email.split("@")[0] && (
                      <span className="text-muted-foreground text-xs truncate">
                        ({u.display_name})
                      </span>
                    )}
                  </button>
                ))}
              </div>
            )}

            {showResults && searching && (
              <div className="absolute z-10 mt-1 w-full rounded-md border border-border bg-background shadow-md px-3 py-2 text-sm text-muted-foreground">
                Searching...
              </div>
            )}

            {showResults &&
              !searching &&
              searchQuery.length >= 2 &&
              filteredResults.length === 0 &&
              searchResults.length === 0 && (
                <div className="absolute z-10 mt-1 w-full rounded-md border border-border bg-background shadow-md px-3 py-2 text-sm text-muted-foreground">
                  No users found
                </div>
              )}
          </div>

          {/* People with access */}
          <div>
            <h4 className="text-sm font-medium mb-2">People with access</h4>
            <div className="space-y-1 rounded-md border border-border divide-y divide-border">
              {/* Owner row */}
              <div className="flex items-center justify-between px-3 py-2">
                <span className="text-sm truncate">{ownerEmail}</span>
                <Badge variant="secondary" className="ml-2 shrink-0">
                  Owner
                </Badge>
              </div>

              {/* Collaborator rows */}
              {collaborators.map((c) => (
                <div
                  key={c.id}
                  className="flex items-center justify-between px-3 py-2"
                >
                  <span className="text-sm truncate">{c.user_email}</span>
                  <div className="flex items-center gap-2 shrink-0 ml-2">
                    <span className="text-xs text-muted-foreground">
                      {c.role}
                    </span>
                    <button
                      onClick={() => removeCollaborator(c.user_email)}
                      className="text-muted-foreground hover:text-destructive"
                      title="Remove collaborator"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
