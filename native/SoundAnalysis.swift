import Foundation
import AVFoundation
import SoundAnalysis

final class FileSoundObserver:NSObject,SNResultsObserving {
    var scores:[String:Double]=[:]
    var count=0
    var windows:[[String:Any]]=[]
    var failure:String?
    var complete=false
    func request(_ request:SNRequest,didProduce result:SNResult) {
        guard let result=result as? SNClassificationResult else { return }
        count += 1
        windows.append(["start":result.timeRange.start.seconds,"end":CMTimeRangeGetEnd(result.timeRange).seconds,"labels":result.classifications.prefix(8).map{["label":$0.identifier,"confidence":$0.confidence]}])
        for c in result.classifications.prefix(12) { scores[c.identifier,default:0] += c.confidence }
    }
    func request(_ request:SNRequest,didFailWithError error:Error) { failure=error.localizedDescription;complete=true }
    func requestDidComplete(_ request:SNRequest) {complete=true}
    func result()->[String:Any] {
        if let error=failure { return ["error":error] }
        return ["labels":scores.sorted{$0.value>$1.value}.prefix(12).map{["label":$0.key,"confidence":$0.value/Double(max(1,count))]},"windows":windows,"model":"Apple SoundAnalysis version1"]
    }
}
func classifyFile(_ path:String)->[String:Any] {
    do {
        let file=try AVAudioFile(forReading:URL(fileURLWithPath:path))
        let duration=Double(file.length)/file.processingFormat.sampleRate
        if duration<1.6 {return ["labels":[],"windows":0,"model":"Apple SoundAnalysis version1","warning":"File shorter than the classifier window. Use metadata and measured features"]}
        let analyzer=try SNAudioFileAnalyzer(url:URL(fileURLWithPath:path))
        let request=try SNClassifySoundRequest(classifierIdentifier:.version1)
        let observer=FileSoundObserver()
        try analyzer.add(request,withObserver:observer)
        analyzer.analyze()
        let deadline=Date(timeIntervalSinceNow:120)
        withExtendedLifetime(analyzer) {
            while !observer.complete && Date()<deadline {RunLoop.current.run(until:Date(timeIntervalSinceNow:0.02))}
        }
        if !observer.complete {return ["error":"SoundAnalysis timed out after 120 seconds"]}
        return observer.result()
    } catch { return ["error":error.localizedDescription] }
}

