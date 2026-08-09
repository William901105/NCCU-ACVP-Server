using System.Runtime.Serialization;

namespace NIST.CVP.ACVTS.Libraries.Crypto.Common.PQC.Enums;

public enum PrivateKeyFormat
{
    [EnumMember(Value = "none")]
    None,
    
    [EnumMember(Value = "seed")]
    Seed,
    
    [EnumMember(Value = "expanded")]
    Expanded
}
