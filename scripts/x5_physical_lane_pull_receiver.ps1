param(
  [string]$SenderAddress = "10.204.0.1",
  [int]$Port = 45850
)

function Read-Exact([System.IO.Stream]$Input, [int]$Length) {
  $buffer = New-Object byte[] $Length
  $offset = 0
  while ($offset -lt $Length) {
    $read = $Input.Read($buffer, $offset, $Length - $offset)
    if ($read -le 0) { throw "peer closed early" }
    $offset += $read
  }
  return ,$buffer
}

$client = [System.Net.Sockets.TcpClient]::new()
try {
  $client.Connect($SenderAddress, $Port)
  $stream = $client.GetStream()
  $headerLength = [System.Net.IPAddress]::NetworkToHostOrder([BitConverter]::ToInt32([byte[]](Read-Exact $stream 4), 0))
  if ($headerLength -lt 2 -or $headerLength -gt 4096) { throw "invalid header length" }
  $header = [System.Text.Encoding]::UTF8.GetString([byte[]](Read-Exact $stream $headerLength)) | ConvertFrom-Json
  $expectedSize = [Int64]$header.object_size
  $hash = [System.Security.Cryptography.SHA256]::Create()
  $remaining = $expectedSize
  while ($remaining -gt 0) {
    $take = [Math]::Min($remaining, 1048576)
    $block = [byte[]](Read-Exact $stream ([int]$take))
    [void]$hash.TransformBlock($block, 0, $block.Length, $block, 0)
    $remaining -= $block.Length
  }
  [void]$hash.TransformFinalBlock([byte[]]::new(0), 0, 0)
  $receivedDigest = "sha256:" + ([BitConverter]::ToString($hash.Hash).Replace("-", "").ToLowerInvariant())
  $verified = ($receivedDigest -eq [string]$header.object_digest)
  $response = @{ verified = $verified; received_digest = $receivedDigest; received_size = $expectedSize } | ConvertTo-Json -Compress
  $responseBytes = [System.Text.Encoding]::UTF8.GetBytes($response)
  $networkLength = [System.Net.IPAddress]::HostToNetworkOrder([int]$responseBytes.Length)
  $stream.Write([BitConverter]::GetBytes($networkLength), 0, 4)
  $stream.Write($responseBytes, 0, $responseBytes.Length)
  Write-Output $response
} finally {
  $client.Close()
}
