"use client"

import * as React from "react"
import { cn } from "@/lib/utils"

interface ScrollAreaProps extends React.HTMLAttributes<HTMLDivElement> {
  orientation?: "vertical" | "horizontal" | "both"
}

const ScrollArea = React.forwardRef<HTMLDivElement, ScrollAreaProps>(
  ({ className, children, orientation = "vertical", ...props }, ref) => (
    <div
      ref={ref}
      className={cn(
        "relative overflow-hidden",
        orientation === "vertical" && "h-full overflow-y-auto",
        orientation === "horizontal" && "w-full overflow-x-auto",
        orientation === "both" && "overflow-auto",
        className
      )}
      {...props}
    >
      {children}
    </div>
  )
)
ScrollArea.displayName = "ScrollArea"

export { ScrollArea }