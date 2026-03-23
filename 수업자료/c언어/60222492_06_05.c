#include <stdio.h>
void main(){
	int num,num2;
	printf("정수 1개를 입력하시오:");
	scanf("%d",&num);
	if(num%2==0)
	{
		num2 = num*num*num+1;
		printf("계산결과:%d",num2);
	}
	else
	{
		num2 = num*num*2+4*num+1;
		printf("계산결과:%d",num2);
		
	}
}
