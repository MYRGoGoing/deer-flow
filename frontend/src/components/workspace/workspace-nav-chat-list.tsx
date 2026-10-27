"use client";

import { Files, MessagesSquare, Search } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import {
  SidebarGroup,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar";

const navigation = [
  { href: "/workspace/knowledge", label: "知识检索", icon: Search },
  { href: "/workspace/knowledge/documents", label: "文档库", icon: Files },
  { href: "/workspace/chats", label: "问答记录", icon: MessagesSquare },
];

export function WorkspaceNavChatList() {
  const pathname = usePathname();
  return (
    <SidebarGroup className="pt-1">
      <SidebarMenu>
        {navigation.map(({ href, label, icon: Icon }) => (
          <SidebarMenuItem key={href}>
            <SidebarMenuButton
              asChild
              isActive={pathname === href}
              tooltip={label}
              className="data-[active=true]:bg-emerald-50 data-[active=true]:text-emerald-800 dark:data-[active=true]:bg-emerald-950 dark:data-[active=true]:text-emerald-200"
            >
              <Link href={href}>
                <Icon />
                <span>{label}</span>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
        ))}
      </SidebarMenu>
    </SidebarGroup>
  );
}
