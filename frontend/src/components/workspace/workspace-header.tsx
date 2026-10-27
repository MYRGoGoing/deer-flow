"use client";

import { BookOpen, MessageSquarePlus } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import {
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarTrigger,
  useSidebar,
} from "@/components/ui/sidebar";
import { cn } from "@/lib/utils";

export function WorkspaceHeader({ className }: { className?: string }) {
  const { state } = useSidebar();
  const pathname = usePathname();
  return (
    <>
      <div
        className={cn(
          "group/workspace-header flex h-16 flex-col justify-center",
          className,
        )}
      >
        {state === "collapsed" ? (
          <div className="group-has-data-[collapsible=icon]/sidebar-wrapper:-translate-y flex w-full cursor-pointer items-center justify-center">
            <div className="block pt-1 text-emerald-700 group-hover/workspace-header:hidden">
              <BookOpen className="size-5" aria-label="企业知识库" />
            </div>
            <SidebarTrigger className="hidden pl-2 group-hover/workspace-header:block" />
          </div>
        ) : (
          <div className="flex items-center justify-between gap-2">
            <Link
              href="/workspace/knowledge"
              className="ml-2 flex min-w-0 items-center gap-2.5"
            >
              <span className="flex size-8 shrink-0 items-center justify-center rounded-md bg-emerald-700 text-white">
                <BookOpen className="size-4" />
              </span>
              <span className="min-w-0">
                <span className="block text-sm font-semibold">企业知识库</span>
                <span className="text-muted-foreground block text-[10px]">
                  TECHNICAL KNOWLEDGE
                </span>
              </span>
            </Link>
            <SidebarTrigger />
          </div>
        )}
      </div>
      <SidebarMenu>
        <SidebarMenuItem>
          <SidebarMenuButton
            isActive={pathname === "/workspace/chats/new"}
            tooltip="新建知识问答"
            asChild
          >
            <Link className="text-muted-foreground" href="/workspace/chats/new">
              <MessageSquarePlus size={16} />
              <span>新建知识问答</span>
            </Link>
          </SidebarMenuButton>
        </SidebarMenuItem>
      </SidebarMenu>
    </>
  );
}
