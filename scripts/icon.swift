import AppKit

let input = URL(fileURLWithPath: CommandLine.arguments[1])
let dest = URL(fileURLWithPath: CommandLine.arguments[2], isDirectory: true)
guard let vector = NSImage(contentsOf: input) else {
    fatalError("Не удалось прочитать SVG иконки MIMIC")
}
try FileManager.default.createDirectory(at: dest, withIntermediateDirectories: true)
for edge in [16, 32, 128, 256, 512] {
    for scale in [1, 2] {
        let size=edge*scale
        guard let bitmap=NSBitmapImageRep(bitmapDataPlanes:nil,pixelsWide:size,pixelsHigh:size,bitsPerSample:8,samplesPerPixel:4,hasAlpha:true,isPlanar:false,colorSpaceName:.deviceRGB,bytesPerRow:0,bitsPerPixel:0),
              let context=NSGraphicsContext(bitmapImageRep:bitmap) else { fatalError("Иконка: недоступен буфер") }
        NSGraphicsContext.saveGraphicsState()
        NSGraphicsContext.current=context
        context.imageInterpolation = .high
        vector.draw(in:NSRect(x:0,y:0,width:CGFloat(size),height:CGFloat(size)),from:.zero,operation:.sourceOver,fraction:1)
        context.flushGraphics()
        NSGraphicsContext.restoreGraphicsState()
        let suffix=scale==2 ? "@2x" : ""
        try bitmap.representation(using:.png,properties:[:])!.write(to:dest.appendingPathComponent("icon_\(edge)x\(edge)\(suffix).png"))
    }
}
