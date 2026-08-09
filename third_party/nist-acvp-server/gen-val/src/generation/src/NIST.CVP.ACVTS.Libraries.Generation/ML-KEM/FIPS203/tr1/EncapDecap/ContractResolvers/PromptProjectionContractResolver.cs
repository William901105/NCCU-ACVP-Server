using System;
using System.Linq;
using Newtonsoft.Json.Serialization;
using NIST.CVP.ACVTS.Libraries.Crypto.Common.PQC.Enums;
using NIST.CVP.ACVTS.Libraries.Crypto.Common.PQC.MLKEM;
using NIST.CVP.ACVTS.Libraries.Generation.Core.ContractResolvers;

namespace NIST.CVP.ACVTS.Libraries.Generation.ML_KEM.FIPS203.tr1.EncapDecap.ContractResolvers;

public class PromptProjectionContractResolver : ProjectionContractResolverBase<TestGroup, TestCase>
{
    protected override Predicate<object> TestGroupSerialization(JsonProperty jsonProperty)
    {
        var includeProperties = new []
        {
            nameof(TestGroup.TestGroupId), 
            nameof(TestGroup.TestType), 
            nameof(TestGroup.ParameterSet),
            nameof(TestGroup.Function),
            nameof(TestGroup.KeyFormat),
            nameof(TestGroup.Tests)
        };
        
        if (includeProperties.Contains(jsonProperty.UnderlyingName, StringComparer.OrdinalIgnoreCase))
        {
            return jsonProperty.ShouldSerialize = _ => true;
        }

        return jsonProperty.ShouldSerialize = _ => false;
    }

    protected override Predicate<object> TestCaseSerialization(JsonProperty jsonProperty)
    {
        var includeProperties = new[]
        {
            nameof(TestCase.TestCaseId)
        };
        
        var includeAllEncapProperties = new []
        {
            nameof(TestCase.EncapsulationKey)
        };
        
        var includeAllDecapProperties = new []
        {
            nameof(TestCase.DecapsulationKey),
            nameof(TestCase.SeedD),
            nameof(TestCase.SeedZ)
        };
        
        var includeExpandedDecapKeyProperties = new []
        {
            nameof(TestCase.DecapsulationKey)
        };
        
        var includeEncapProperties = new[]
        {
            nameof(TestCase.SeedM)
        };
        
        var includeDecapProperties = new[]
        {
            nameof(TestCase.Ciphertext)
        };

        if (includeProperties.Contains(jsonProperty.UnderlyingName, StringComparer.OrdinalIgnoreCase))
        {
            return jsonProperty.ShouldSerialize = _ => true;
        }

        if (includeEncapProperties.Contains(jsonProperty.UnderlyingName, StringComparer.OrdinalIgnoreCase))
        {
            return jsonProperty.ShouldSerialize = instance =>
            {
                GetTestCaseFromTestCaseObject(instance, out var group, out var testCase);
                return group.Function == MLKEMFunction.Encapsulation;
            };
        }
        
        if (includeDecapProperties.Contains(jsonProperty.UnderlyingName, StringComparer.OrdinalIgnoreCase))
        {
            return jsonProperty.ShouldSerialize = instance =>
            {
                GetTestCaseFromTestCaseObject(instance, out var group, out var testCase);
                return group.Function == MLKEMFunction.Decapsulation;
            };
        }
        
        if (includeAllEncapProperties.Contains(jsonProperty.UnderlyingName, StringComparer.OrdinalIgnoreCase))
        {
            return jsonProperty.ShouldSerialize = instance =>
            {
                GetTestCaseFromTestCaseObject(instance, out var group, out var testCase);
                return group.Function is MLKEMFunction.Encapsulation or MLKEMFunction.EncapsulationKeyCheck;
            };
        }
        
        if (includeAllDecapProperties.Contains(jsonProperty.UnderlyingName, StringComparer.OrdinalIgnoreCase))
        {
            return jsonProperty.ShouldSerialize = instance =>
            {
                GetTestCaseFromTestCaseObject(instance, out var group, out var testCase);
                if (group.Function is MLKEMFunction.Decapsulation or MLKEMFunction.DecapsulationKeyCheck)
                {
                    if (includeExpandedDecapKeyProperties.Contains(jsonProperty.UnderlyingName,
                            StringComparer.OrdinalIgnoreCase))
                    {
                        return group.KeyFormat == PrivateKeyFormat.Expanded;
                    }
                    else
                    {
                        return group.KeyFormat == PrivateKeyFormat.Seed;
                    }
                }
                else
                {
                    return false;
                }
            };
        }
        
        return jsonProperty.ShouldSerialize = _ => false;
    }
}
