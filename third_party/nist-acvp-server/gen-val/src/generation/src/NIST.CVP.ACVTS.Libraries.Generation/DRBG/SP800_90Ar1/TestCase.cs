using System.Collections.Generic;
using Newtonsoft.Json;
using NIST.CVP.ACVTS.Libraries.Generation.Core;
using NIST.CVP.ACVTS.Libraries.Math;

namespace NIST.CVP.ACVTS.Libraries.Generation.DRBG.SP800_90Ar1
{
    public class TestCase : ITestCase<TestGroup, TestCase>
    {
        public int TestCaseId { get; set; }
        [JsonIgnore]
        public bool? TestPassed => true;
        [JsonIgnore]
        public bool Deferred => false;
        public TestGroup ParentGroup { get; set; }
        [JsonProperty(PropertyName = "entropyInput")]
        public BitString EntropyInput { get; set; }
        [JsonProperty(PropertyName = "nonce")]
        public BitString Nonce { get; set; }
        [JsonProperty(PropertyName = "persoString")]
        public BitString PersoString { get; set; }
        [JsonProperty(PropertyName = "otherInput")]
        public List<SP800_90Ar1.OtherInput> OtherInput { get; set; } = new List<SP800_90Ar1.OtherInput>();
        [JsonProperty(PropertyName = "returnedBits")]
        public BitString ReturnedBits { get; set; }
    }
    
    public class OtherInput
    {
        [JsonProperty(PropertyName = "intendedUse")]
        public string IntendedUse { get; set; }
        [JsonProperty(PropertyName = "additionalInput")]
        public BitString AdditionalInput { get; set; }
        [JsonProperty(PropertyName = "entropyInput")]
        public BitString EntropyInput { get; set; }
    }
}
