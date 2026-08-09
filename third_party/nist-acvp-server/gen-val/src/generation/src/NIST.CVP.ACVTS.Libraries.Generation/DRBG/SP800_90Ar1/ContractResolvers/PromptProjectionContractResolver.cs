using System;
using System.Linq;
using Newtonsoft.Json.Serialization;
using NIST.CVP.ACVTS.Libraries.Generation.Core.ContractResolvers;

namespace NIST.CVP.ACVTS.Libraries.Generation.DRBG.SP800_90Ar1.ContractResolvers
{
    public class PromptProjectionContractResolver : ProjectionContractResolverBase<TestGroup, TestCase>
    {
        /// <summary>
        /// Every group property included
        /// </summary>
        /// <param name="jsonProperty"></param>
        /// <returns></returns>
        protected override Predicate<object> TestGroupSerialization(JsonProperty jsonProperty)
        {
            var includeProperties = new[]
            {
                nameof(TestGroup.CounterFieldLength)
            };
            
            if (includeProperties.Contains(jsonProperty.UnderlyingName, StringComparer.OrdinalIgnoreCase))
            {
                return jsonProperty.ShouldSerialize = instance =>
                {
                    GetTestGroupFromTestGroupObject(instance, out var testGroup);
                    return (testGroup.Mode.ToString().Contains("aes", StringComparison.OrdinalIgnoreCase) || testGroup.Mode.ToString().Contains("tdes", StringComparison.OrdinalIgnoreCase));
                };
            }
            
            return jsonProperty.ShouldSerialize = instance => true;
        }


        protected override Predicate<object> TestCaseSerialization(JsonProperty jsonProperty)
        {
            var excludeProperties = new[]
            {
                nameof(TestCase.ReturnedBits),
                nameof(TestCase.Deferred),
                nameof(TestCase.TestPassed),
            };

            if (excludeProperties.Contains(jsonProperty.UnderlyingName, StringComparer.OrdinalIgnoreCase))
            {
                return jsonProperty.ShouldSerialize =
                    instance => false;
            }

            return jsonProperty.ShouldSerialize = instance => true;
        }
    }
}
