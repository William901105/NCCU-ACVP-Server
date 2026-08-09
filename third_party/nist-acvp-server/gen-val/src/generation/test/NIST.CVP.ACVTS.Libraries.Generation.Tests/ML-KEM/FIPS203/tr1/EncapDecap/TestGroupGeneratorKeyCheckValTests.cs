using System.Threading.Tasks;
using NIST.CVP.ACVTS.Libraries.Crypto.Common.PQC.Enums;
using NIST.CVP.ACVTS.Libraries.Crypto.Common.PQC.MLKEM;
using NIST.CVP.ACVTS.Libraries.Generation.ML_KEM.FIPS203.tr1.EncapDecap;
using NIST.CVP.ACVTS.Tests.Core.TestCategoryAttributes;
using NUnit.Framework;

namespace NIST.CVP.ACVTS.Libraries.Generation.Tests.ML_KEM.FIPS203.tr1.EncapDecap;

[TestFixture, UnitTest]
public class TestGroupGeneratorKeyCheckValTests
{
    [Test]
    public async Task ShouldUseExpandedKeyFormatForDecapsulationKeyCheck()
    {
        var subject = new TestGroupGeneratorKeyCheckVal();
        var parameters = new Parameters
        {
            ParameterSets = [MLKEMParameterSet.ML_KEM_512],
            Functions = [MLKEMFunction.DecapsulationKeyCheck],
            KeyFormats = [PrivateKeyFormat.Seed, PrivateKeyFormat.Expanded]
        };

        var result = await subject.BuildTestGroupsAsync(parameters);

        Assert.That(result, Has.Count.EqualTo(1));
        Assert.That(result[0].Function, Is.EqualTo(MLKEMFunction.DecapsulationKeyCheck));
        Assert.That(result[0].KeyFormat, Is.EqualTo(PrivateKeyFormat.Expanded));
    }
}
